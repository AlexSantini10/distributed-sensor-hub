"""Store node-local replicated sensor state under LWW semantics.

Responsibilities:
    - Hold the winning record for each logical sensor identifier.
    - Apply deterministic LWW conflict resolution using ``(ts_ms, origin)`` ordering.
    - Maintain separate incremental buffers for UI snapshots and replication gossip.
    - Expose stable snapshot shapes expected by the UI, Web API, and tests.
"""

from copy import deepcopy
from collections import deque
from dataclasses import dataclass
import threading

from state.contracts import StoreMergeOutcome
from state.policy import LwwMergePolicy, MergeDecision, MergePolicy
from utils.typing import (
    JsonObject,
    JsonValue,
    NodeSnapshot,
    ReplicationDeltaBatch,
    ReplicationDeltaDict,
    SensorMetaDict,
    SensorRecordDict,
)


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


@dataclass(frozen=True)
class _ReplicationDelta:
    """Store one ordered replication delta entry in the ring buffer."""

    seq: int
    sensor_id: str
    record: SensorRecord


class NodeStateStore:
    """Maintain thread-safe replicated sensor state and incremental buffers.

    Attributes:
        _lock (threading.Lock): Mutex protecting state and update-buffer mutations.
        _state (dict[str, SensorRecord]): Current LWW winner for each logical ``sensor_id``.
        _updates_ui (dict[str, SensorRecord]): Pending records not yet drained by the UI/Web API consumer.
        _replication_deltas (deque[_ReplicationDelta]): Ordered bounded replication delta buffer.
        _replication_next_seq (int): Monotonic sequence assigned to appended delta entries.
        _replication_last_read_seq (int): Sequence cursor for drain operations.
    """

    def __init__(
        self,
        replication_delta_maxlen: int = 512,
        merge_policy: MergePolicy | None = None,
    ) -> None:
        """Initialize empty state and update buffers.

        Returns:
            None: This constructor does not return a value.
        """
        if replication_delta_maxlen <= 0:
            raise ValueError("replication_delta_maxlen must be > 0")
        self._lock = threading.Lock()
        self._state: dict[str, SensorRecord] = {}
        self._updates_ui: dict[str, SensorRecord] = {}
        self._updates_ui_sources: dict[str, str] = {}
        self._replication_deltas: deque[_ReplicationDelta] = deque(maxlen=replication_delta_maxlen)
        self._replication_next_seq = 0
        self._replication_last_read_seq = 0
        self._merge_policy: MergePolicy = merge_policy or LwwMergePolicy()

    def _apply_winner(self, sensor_id: str, record: SensorRecord, *, ui_source: str) -> None:
        """Store one winning record across state and incremental buffers.

        Args:
            sensor_id (str): Logical sensor identifier.
            record (SensorRecord): Winning record to materialize.
            ui_source (str): Attribution label for the UI updates buffer.

        Returns:
            None: This method mutates state and both incremental buffers.
        """
        self._state[sensor_id] = record
        self._updates_ui[sensor_id] = record
        self._updates_ui_sources[sensor_id] = ui_source
        self._replication_deltas.append(
            _ReplicationDelta(
                seq=self._replication_next_seq,
                sensor_id=sensor_id,
                record=record,
            )
        )
        self._replication_next_seq += 1

    def _decide_merge(self, current: SensorRecord, candidate: SensorRecord) -> MergeDecision:
        """Delegate merge decision to the configured policy."""
        return self._merge_policy.decide(current=current, candidate=candidate)

    def _parse_timestamp(self, value: object) -> int | None:
        """Normalize a timestamp candidate into an integer when valid."""
        if not isinstance(value, int):
            return None
        return value

    def _candidate_from_flat_entry(
        self,
        sensor_id: object,
        raw_value: object,
    ) -> tuple[str, SensorRecord] | None:
        """Build one merge candidate from flat full-state shape entries."""
        if not isinstance(sensor_id, str) or sensor_id == "":
            return None
        if not isinstance(raw_value, dict):
            return None
        if "value" not in raw_value:
            return None
        if "timestamp" not in raw_value and "ts_ms" not in raw_value:
            return None

        ts_value = self._parse_timestamp(raw_value.get("timestamp", raw_value.get("ts_ms")))
        if ts_value is None:
            return None

        origin_value = raw_value.get("origin")
        if not isinstance(origin_value, str):
            origin_value = ""

        return (
            sensor_id,
            SensorRecord(
                value=raw_value.get("value"),
                ts_ms=ts_value,
                origin=origin_value,
                meta=SensorMeta.from_dict(raw_value.get("meta", {})),
            ),
        )

    def _candidate_from_grouped_entry(
        self,
        global_sensor_id: object,
        raw_record: object,
    ) -> tuple[str, SensorRecord] | None:
        """Build one merge candidate from grouped full-state shape entries."""
        if not isinstance(raw_record, dict):
            return None
        if "value" not in raw_record:
            return None
        if "timestamp" not in raw_record and "ts_ms" not in raw_record:
            return None

        ts_value = self._parse_timestamp(raw_record.get("timestamp", raw_record.get("ts_ms")))
        if ts_value is None:
            return None

        sensor_id = global_sensor_id
        inferred_origin = ""
        if isinstance(global_sensor_id, str) and ":" in global_sensor_id:
            inferred_origin, sensor_id = global_sensor_id.split(":", 1)

        if not isinstance(sensor_id, str) or sensor_id == "":
            return None

        origin_value = raw_record.get("origin")
        if not isinstance(origin_value, str):
            origin_value = inferred_origin if isinstance(inferred_origin, str) else ""

        return (
            sensor_id,
            SensorRecord(
                value=raw_record.get("value"),
                ts_ms=ts_value,
                origin=origin_value,
                meta=SensorMeta.from_dict(raw_record.get("meta", {})),
            ),
        )

    def _collect_merge_candidates(
        self,
        remote_full_state: JsonObject | NodeSnapshot,
    ) -> tuple[list[tuple[str, SensorRecord]], int]:
        """Extract normalized merge candidates from supported full-state payload shapes."""
        candidates: list[tuple[str, SensorRecord]] = []
        invalid_entries = 0

        for key, value in remote_full_state.items():
            flat_candidate = self._candidate_from_flat_entry(sensor_id=key, raw_value=value)
            if flat_candidate is not None:
                candidates.append(flat_candidate)
                continue

            if not isinstance(value, dict):
                invalid_entries += 1
                continue

            grouped_found = False
            for global_sensor_id, record_value in value.items():
                grouped_candidate = self._candidate_from_grouped_entry(
                    global_sensor_id=global_sensor_id,
                    raw_record=record_value,
                )
                if grouped_candidate is not None:
                    candidates.append(grouped_candidate)
                    grouped_found = True
                else:
                    invalid_entries += 1

            if not grouped_found and len(value) == 0:
                invalid_entries += 1

        return candidates, invalid_entries

    def _merge_lww(
        self,
        sensor_id: str,
        update: SensorRecord,
        *,
        ui_source: str,
    ) -> StoreMergeOutcome:
        """Merge one candidate update into the internal LWW register set.

        Args:
            sensor_id (str): Logical sensor key shared across competing origins.
            update (SensorRecord): Candidate record to compare against the current winner.
            ui_source (str): UI attribution label attached when the update wins.

        Returns:
            tuple[bool, str, SensorRecord | None]: Merge outcome containing an applied flag,
                a reason code, and the previous winning record when one existed.
        """
        with self._lock:
            prev = self._state.get(sensor_id)
            if prev is None:
                self._apply_winner(sensor_id=sensor_id, record=update, ui_source=ui_source)
                return True, "insert", None

            decision = self._decide_merge(current=prev, candidate=update)
            if decision != "stale":
                self._apply_winner(sensor_id=sensor_id, record=update, ui_source=ui_source)
                return True, decision, prev

            return False, "stale", prev

    def merge_record(
        self,
        sensor_id: str,
        update: SensorRecord,
        ui_source: str = "unknown",
    ) -> StoreMergeOutcome:
        """Merge one normalized record into the store using the configured policy.

        Args:
            sensor_id (str): Logical sensor key shared across competing origins.
            update (SensorRecord): Candidate record to compare against the current winner.
            ui_source (str): UI attribution label attached when the update wins.

        Returns:
            StoreMergeOutcome: Merge outcome containing the applied flag, reason, and
                previous winning record when one existed.
        """
        return self._merge_lww(sensor_id=sensor_id, update=update, ui_source=ui_source)

    def apply_update(
        self,
        sensor_id: str,
        value: JsonValue,
        timestamp: int,
        origin: str = "",
        meta: JsonObject | SensorMetaDict | None = None,
    ) -> bool:
        """Apply one update under LWW semantics.

        Args:
            sensor_id (str): Logical sensor identifier.
            value (JsonValue): Candidate sensor value.
            timestamp (int): Candidate timestamp in milliseconds.
            origin (str): Optional update origin used as deterministic tie-break key.
            meta (JsonObject | SensorMetaDict | None): Optional metadata carried with
                the sensor value.

        Returns:
            bool: ``True`` if the candidate becomes the current winner.
        """
        if not isinstance(sensor_id, str) or sensor_id == "":
            return False
        if not isinstance(timestamp, int):
            return False
        if not isinstance(origin, str):
            origin = ""
        if meta is None:
            meta = {}

        candidate = SensorRecord(
            value=value,
            ts_ms=timestamp,
            origin=origin,
            meta=SensorMeta.from_dict(meta),
        )
        applied, _, _ = self.merge_record(sensor_id=sensor_id, update=candidate)
        return applied

    def merge_state(
        self,
        remote_full_state: JsonObject | NodeSnapshot,
        reject_partial: bool = False,
        ui_source: str = "full_sync",
    ) -> int:
        """Bulk-merge a remote full-state payload under LWW semantics.

        Supported shapes:
            1) ``{sensor_id: {"value": ..., "timestamp": ...}}``
            2) ``{node_id: {origin:sensor_id: {"value": ..., "ts_ms": ..., ...}}}``

        Args:
            remote_full_state (JsonObject): Full-state payload received from a peer.
            reject_partial (bool): Whether malformed entries should reject the whole batch.
            ui_source (str): UI attribution label attached to applied winners.

        Returns:
            int: Number of updates that became winners locally.
        """
        if not isinstance(remote_full_state, dict):
            return 0

        candidates, invalid_entries = self._collect_merge_candidates(
            remote_full_state=remote_full_state
        )
        if reject_partial and invalid_entries > 0:
            return 0

        with self._lock:
            applied = 0
            for sensor_id, candidate in candidates:
                prev = self._state.get(sensor_id)
                if prev is None:
                    self._apply_winner(
                        sensor_id=sensor_id,
                        record=candidate,
                        ui_source=ui_source,
                    )
                    applied += 1
                    continue

                if self._decide_merge(current=prev, candidate=candidate) != "stale":
                    self._apply_winner(
                        sensor_id=sensor_id,
                        record=candidate,
                        ui_source=ui_source,
                    )
                    applied += 1

            return applied

    def upsert(self, sensor_id: str, record: SensorRecord) -> None:
        """Force one record into state and both incremental buffers.

        Args:
            sensor_id (str): Logical sensor identifier to overwrite.
            record (SensorRecord): Record to expose to state, UI, and replication consumers.

        Returns:
            None: This method mutates the store in place.
        """
        with self._lock:
            self._apply_winner(sensor_id=sensor_id, record=record, ui_source="upsert")

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
            self._updates_ui_sources.pop(sensor_id, None)
            return existed

    def clear(self) -> None:
        """Remove all state and buffered incremental updates.

        Returns:
            None: This method mutates the store in place.
        """
        with self._lock:
            self._state.clear()
            self._updates_ui.clear()
            self._updates_ui_sources.clear()
            self._replication_deltas.clear()
            self._replication_last_read_seq = self._replication_next_seq

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
            NodeSnapshot: Incremental snapshot containing only records not yet
                consumed by the UI, enriched with optional ``sync_source``.
        """
        with self._lock:
            per_node: dict[str, SensorRecordDict] = {}
            for sensor_id, record in self._updates_ui.items():
                origin = record.origin
                if not isinstance(origin, str) or origin == "":
                    origin = node_id
                global_sensor_id = f"{origin}:{sensor_id}"
                row = record.to_dict()
                row["sync_source"] = self._updates_ui_sources.get(sensor_id, "unknown")
                per_node[global_sensor_id] = row
            snapshot: NodeSnapshot = {node_id: per_node}
            self._updates_ui.clear()
            self._updates_ui_sources.clear()
            return snapshot

    def pop_replication_updates(self, node_id: str) -> NodeSnapshot:
        """Drain the replication buffer into one gossip payload snapshot.

        Args:
            node_id (str): Local node identifier used as the outer grouping key.

        Returns:
            NodeSnapshot: Incremental replication snapshot keyed by global sensor identifier.
        """
        with self._lock:
            drained = self._drain_replication_deltas_locked()
            per_node: dict[str, SensorRecordDict] = {}
            for delta in drained:
                sensor_id = delta.sensor_id
                record = delta.record
                origin = record.origin
                if not isinstance(origin, str) or origin == "":
                    origin = node_id
                global_sensor_id = f"{origin}:{sensor_id}"
                per_node[global_sensor_id] = record.to_dict()
            return {node_id: per_node}

    def pop_replication_deltas(self) -> ReplicationDeltaBatch:
        """Drain ordered replication deltas from the internal bounded ring buffer.

        Returns:
            ReplicationDeltaBatch: Ordered delta events in append order.
        """
        with self._lock:
            drained = self._drain_replication_deltas_locked()
            return tuple(self._delta_to_dict(delta) for delta in drained)

    def get_replication_deltas_since(
        self,
        *,
        since_ts_ms: int,
    ) -> ReplicationDeltaBatch | None:
        """Return ordered deltas newer than ``since_ts_ms`` without draining.

        Returns ``None`` when the requested cursor is older than the retained
        bounded history and a full sync is required.
        """
        with self._lock:
            if not self._replication_deltas:
                return ()

            oldest_ts_ms = self._replication_deltas[0].record.ts_ms
            if since_ts_ms < oldest_ts_ms:
                return None

            selected = [
                delta
                for delta in self._replication_deltas
                if delta.record.ts_ms > since_ts_ms
            ]
            return tuple(self._delta_to_dict(delta) for delta in selected)

    def get_latest_timestamp_for_origin(self, origin: str) -> int:
        """Return the latest winning timestamp known for one origin.

        Args:
            origin (str): Origin node identifier.

        Returns:
            int: Maximum ``ts_ms`` among current winners for ``origin``, or ``0``.
        """
        if not isinstance(origin, str) or origin == "":
            return 0
        with self._lock:
            latest = 0
            for record in self._state.values():
                if record.origin != origin:
                    continue
                if record.ts_ms > latest:
                    latest = record.ts_ms
            return latest

    def _drain_replication_deltas_locked(self) -> list[_ReplicationDelta]:
        """Return unread replication deltas and advance the read cursor.

        Caller must hold ``_lock``.
        """
        if not self._replication_deltas:
            self._replication_last_read_seq = self._replication_next_seq
            return []

        first_seq = self._replication_deltas[0].seq
        read_from = max(self._replication_last_read_seq, first_seq)
        drained = [delta for delta in self._replication_deltas if delta.seq >= read_from]
        self._replication_last_read_seq = self._replication_next_seq
        return drained

    @staticmethod
    def _delta_to_dict(delta: _ReplicationDelta) -> ReplicationDeltaDict:
        """Serialize one internal replication delta entry."""
        return {
            "sensor_id": delta.sensor_id,
            "value": delta.record.value,
            "ts_ms": delta.record.ts_ms,
            "origin": delta.record.origin,
            "meta": delta.record.meta.to_dict(),
        }

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
