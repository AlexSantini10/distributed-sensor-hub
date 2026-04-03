"""Store node-local replicated sensor state under LWW semantics.

Responsibilities:
    - Hold the winning record for each logical sensor identifier.
    - Apply deterministic LWW conflict resolution using ``(ts_ms, origin)`` ordering.
    - Maintain separate incremental buffers for UI snapshots and replication gossip.
    - Expose stable snapshot shapes expected by the UI, Web API, and tests.
"""

from copy import deepcopy
from dataclasses import dataclass
import threading

from utils.typing import JsonObject, JsonValue, NodeSnapshot, SensorMetaDict, SensorRecordDict


@dataclass
class SensorMeta:
    """Store normalized metadata associated with one sensor record.

    Attributes:
        unit (JsonValue): Measurement unit propagated with the sensor sample.
        period_ms (JsonValue): Sensor sampling period metadata propagated with the sample.
    """

    unit: JsonValue = None
    period_ms: JsonValue = None

    @staticmethod
    def from_dict(meta: object) -> "SensorMeta":
        """Normalize arbitrary metadata into the supported metadata schema.

        Args:
            meta (object): Input metadata object received from a sensor or network message.

        Returns:
            SensorMeta: Metadata instance with unsupported input coerced to empty defaults.
        """
        if not isinstance(meta, dict):
            meta = {}
        return SensorMeta(
            unit=meta.get("unit"),
            period_ms=meta.get("period_ms"),
        )

    def to_dict(self) -> SensorMetaDict:
        """Serialize metadata into the wire and snapshot representation.

        Returns:
            SensorMetaDict: Mapping containing the normalized ``unit`` and ``period_ms`` fields.
        """
        return {
            "unit": self.unit,
            "period_ms": self.period_ms,
        }


@dataclass
class SensorRecord:
    """Represent the current LWW winner for one logical sensor.

    Attributes:
        value (JsonValue): Winning sensor value.
        ts_ms (int): Primary LWW ordering key in milliseconds.
        origin (str): Secondary LWW tie-break key identifying the winning node.
        meta (SensorMeta): Metadata associated with the winning value.
    """

    value: JsonValue
    ts_ms: int
    origin: str
    meta: SensorMeta

    def to_dict(self) -> SensorRecordDict:
        """Serialize the record into a snapshot-safe mapping.

        Returns:
            SensorRecordDict: Mapping that preserves the record fields expected by
                replication and UI code.
        """
        return {
            "value": self.value,
            "ts_ms": self.ts_ms,
            "origin": self.origin,
            "meta": self.meta.to_dict(),
        }


class NodeStateStore:
    """Maintain thread-safe replicated sensor state and incremental buffers.

    Attributes:
        _lock (threading.Lock): Mutex protecting state and update-buffer mutations.
        _state (dict[str, SensorRecord]): Current LWW winner for each logical ``sensor_id``.
        _updates_ui (dict[str, SensorRecord]): Pending records not yet drained by the UI/Web API consumer.
        _updates_replication (dict[str, SensorRecord]): Pending records not yet drained by the gossip publisher.
    """

    def __init__(self) -> None:
        """Initialize empty state and update buffers.

        Returns:
            None: This constructor does not return a value.
        """
        self._lock = threading.Lock()
        self._state: dict[str, SensorRecord] = {}
        self._updates_ui: dict[str, SensorRecord] = {}
        self._updates_replication: dict[str, SensorRecord] = {}

    def merge_lww(self, sensor_id: str, update: SensorRecord) -> tuple[bool, str, SensorRecord | None]:
        """Merge one candidate update into the LWW register set.

        Args:
            sensor_id (str): Logical sensor key shared across competing origins.
            update (SensorRecord): Candidate record to compare against the current winner.

        Returns:
            tuple[bool, str, SensorRecord | None]: Merge outcome containing an applied flag,
                a reason code, and the previous winning record when one existed.
        """
        with self._lock:
            prev = self._state.get(sensor_id)
            if prev is None:
                self._state[sensor_id] = update
                self._updates_ui[sensor_id] = update
                self._updates_replication[sensor_id] = update
                return True, "insert", None

            if update.ts_ms > prev.ts_ms:
                self._state[sensor_id] = update
                self._updates_ui[sensor_id] = update
                self._updates_replication[sensor_id] = update
                return True, "newer_ts", prev

            if update.ts_ms == prev.ts_ms and update.origin > prev.origin:
                self._state[sensor_id] = update
                self._updates_ui[sensor_id] = update
                self._updates_replication[sensor_id] = update
                return True, "tie_break", prev

            return False, "stale", prev

    def upsert(self, sensor_id: str, record: SensorRecord) -> None:
        """Force one record into state and both incremental buffers.

        Args:
            sensor_id (str): Logical sensor identifier to overwrite.
            record (SensorRecord): Record to expose to state, UI, and replication consumers.

        Returns:
            None: This method mutates the store in place.
        """
        with self._lock:
            self._state[sensor_id] = record
            self._updates_ui[sensor_id] = record
            self._updates_replication[sensor_id] = record

    def remove(self, sensor_id: str) -> bool:
        """Delete one logical sensor from state and pending buffers.

        Args:
            sensor_id (str): Logical sensor identifier to remove.

        Returns:
            bool: ``True`` if the sensor existed in state before removal.
        """
        with self._lock:
            existed = sensor_id in self._state
            self._state.pop(sensor_id, None)
            self._updates_ui.pop(sensor_id, None)
            self._updates_replication.pop(sensor_id, None)
            return existed

    def clear(self) -> None:
        """Remove all state and buffered incremental updates.

        Returns:
            None: This method mutates the store in place.
        """
        with self._lock:
            self._state.clear()
            self._updates_ui.clear()
            self._updates_replication.clear()

    def _snapshot_grouped_for_ui(
        self,
        state_map: dict[str, SensorRecord],
        node_id: str,
    ) -> NodeSnapshot:
        """Project records into the UI/Web API snapshot schema.

        Args:
            state_map (dict): Mapping of logical sensor identifiers to winning records.
            node_id (str): Local node identifier used as the outer grouping key.

        Returns:
            NodeSnapshot: Snapshot grouped by local node id with keys of the form
                ``origin:sensor_id``.
        """
        per_node: dict[str, SensorRecordDict] = {}
        for sensor_id, record in state_map.items():
            origin = record.origin
            if not isinstance(origin, str) or origin == "":
                origin = node_id
            global_sensor_id = f"{origin}:{sensor_id}"
            per_node[global_sensor_id] = record.to_dict()
        return {node_id: per_node}

    def get_state_snapshot(self, node_id: str) -> NodeSnapshot:
        """Return a full snapshot of current LWW winners.

        Args:
            node_id (str): Local node identifier used as the outer grouping key.

        Returns:
            NodeSnapshot: Full state snapshot for UI and HTTP consumers.
        """
        with self._lock:
            return self._snapshot_grouped_for_ui(dict(self._state), node_id)

    def get_updates_snapshot(self, node_id: str) -> NodeSnapshot:
        """Drain the UI update buffer into one incremental snapshot.

        Args:
            node_id (str): Local node identifier used as the outer grouping key.

        Returns:
            NodeSnapshot: Incremental snapshot containing only records not yet consumed by the UI.
        """
        with self._lock:
            snapshot = self._snapshot_grouped_for_ui(dict(self._updates_ui), node_id)
            self._updates_ui.clear()
            return snapshot

    def pop_replication_updates(self, node_id: str) -> NodeSnapshot:
        """Drain the replication buffer into one gossip payload snapshot.

        Args:
            node_id (str): Local node identifier used as the outer grouping key.

        Returns:
            NodeSnapshot: Incremental replication snapshot keyed by global sensor identifier.
        """
        with self._lock:
            per_node: dict[str, SensorRecordDict] = {}
            for sensor_id, record in self._updates_replication.items():
                origin = record.origin
                if not isinstance(origin, str) or origin == "":
                    origin = node_id
                global_sensor_id = f"{origin}:{sensor_id}"
                per_node[global_sensor_id] = record.to_dict()

            self._updates_replication.clear()
            return {node_id: per_node}

    def dump_full_state(self) -> JsonObject:
        """Return a deterministic inspection view grouped by winning origin.

        Args:
            None

        Returns:
            JsonObject: Summary grouped by origin with sorted sensor lists for stable assertions.
        """
        with self._lock:
            state_copy = dict(self._state)

        by_origin: dict[str, JsonObject] = {}
        for sensor_id, rec in state_copy.items():
            origin = rec.origin
            if not isinstance(origin, str) or origin == "":
                origin = "UNKNOWN"

            item: JsonObject = {
                "sensor_id": sensor_id,
                "ts_ms": rec.ts_ms,
                "value": rec.value,
                "unit": rec.meta.unit,
                "period_ms": rec.meta.period_ms,
            }

            bucket = by_origin.get(origin)
            if bucket is None:
                bucket = {"count": 0, "sensors": []}
                by_origin[origin] = bucket

            sensors = bucket["sensors"]
            count = bucket["count"]
            if isinstance(sensors, list):
                sensors.append(item)
            if isinstance(count, int):
                bucket["count"] = count + 1

        for origin in by_origin:
            sensors = by_origin[origin].get("sensors")
            if isinstance(sensors, list):
                sensors.sort(
                    key=lambda item: str(item.get("sensor_id")) if isinstance(item, dict) else ""
                )

        return {
            "by_origin": dict(sorted(by_origin.items(), key=lambda kv: kv[0])),
            "total": len(state_copy),
        }

    def get_items_for_logging(self) -> list[tuple[str, SensorRecord]]:
        """Copy state records into a stable order for structured logging.

        Returns:
            list[tuple[str, SensorRecord]]: Deep-copied records sorted by origin and sensor id.
        """
        with self._lock:
            items = [(sensor_id, deepcopy(rec)) for sensor_id, rec in self._state.items()]
        items.sort(key=lambda kv: (str(kv[1].origin), kv[0]))
        return items
