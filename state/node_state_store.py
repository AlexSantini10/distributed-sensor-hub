from copy import deepcopy
from dataclasses import dataclass
import threading
from typing import Any


@dataclass
class SensorMeta:
    """Normalized sensor metadata kept alongside each state record."""

    unit: Any = None
    period_ms: Any = None

    @staticmethod
    def from_dict(meta) -> "SensorMeta":
        if not isinstance(meta, dict):
            meta = {}
        return SensorMeta(
            unit=meta.get("unit"),
            period_ms=meta.get("period_ms"),
        )

    def to_dict(self):
        return {
            "unit": self.unit,
            "period_ms": self.period_ms,
        }


@dataclass
class SensorRecord:
    """Single LWW record for a logical sensor."""

    value: Any
    ts_ms: int
    origin: str
    meta: SensorMeta

    def to_dict(self):
        return {
            "value": self.value,
            "ts_ms": self.ts_ms,
            "origin": self.origin,
            "meta": self.meta.to_dict(),
        }


class NodeStateStore:
    """Thread-safe state store with LWW merge and snapshot buffers."""

    def __init__(self):
        self._lock = threading.Lock()

        # sensor_id -> SensorRecord
        self._state = {}

        # sensor_id -> SensorRecord
        self._updates_ui = {}

        # sensor_id -> SensorRecord
        self._updates_replication = {}

    def merge_lww(self, sensor_id: str, update: SensorRecord):
        """
        Apply LWW merge.

        Returns:
        - (True, "insert" | "newer_ts" | "tie_break", previous_record_or_none)
        - (False, "stale", previous_record)
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
        """Force insert/update and mark record as updated for both consumers."""
        with self._lock:
            self._state[sensor_id] = record
            self._updates_ui[sensor_id] = record
            self._updates_replication[sensor_id] = record

    def remove(self, sensor_id: str) -> bool:
        """Remove a sensor from state and pending update buffers."""
        with self._lock:
            existed = sensor_id in self._state
            self._state.pop(sensor_id, None)
            self._updates_ui.pop(sensor_id, None)
            self._updates_replication.pop(sensor_id, None)
            return existed

    def clear(self) -> None:
        """Remove every sensor and pending update."""
        with self._lock:
            self._state.clear()
            self._updates_ui.clear()
            self._updates_replication.clear()

    def _snapshot_grouped_for_ui(self, state_map, node_id: str):
        per_node = {}
        for sensor_id, record in state_map.items():
            origin = record.origin
            if not isinstance(origin, str) or origin == "":
                origin = node_id
            global_sensor_id = f"{origin}:{sensor_id}"
            per_node[global_sensor_id] = record.to_dict()
        return {node_id: per_node}

    def get_state_snapshot(self, node_id: str):
        with self._lock:
            return self._snapshot_grouped_for_ui(dict(self._state), node_id)

    def get_updates_snapshot(self, node_id: str):
        with self._lock:
            snapshot = self._snapshot_grouped_for_ui(dict(self._updates_ui), node_id)
            self._updates_ui.clear()
            return snapshot

    def pop_replication_updates(self, node_id: str):
        with self._lock:
            per_node = {}
            for sensor_id, record in self._updates_replication.items():
                origin = record.origin
                if not isinstance(origin, str) or origin == "":
                    origin = node_id
                global_sensor_id = f"{origin}:{sensor_id}"
                per_node[global_sensor_id] = record.to_dict()

            self._updates_replication.clear()
            return {node_id: per_node}

    def dump_full_state(self):
        """Return deterministic state grouped by winner origin."""
        with self._lock:
            state_copy = dict(self._state)

        by_origin = {}
        for sensor_id, rec in state_copy.items():
            origin = rec.origin
            if not isinstance(origin, str) or origin == "":
                origin = "UNKNOWN"

            item = {
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

            bucket["sensors"].append(item)
            bucket["count"] += 1

        for origin in by_origin:
            by_origin[origin]["sensors"].sort(key=lambda x: x["sensor_id"])

        return {
            "by_origin": dict(sorted(by_origin.items(), key=lambda kv: kv[0])),
            "total": len(state_copy),
        }

    def get_items_for_logging(self):
        with self._lock:
            items = [(sensor_id, deepcopy(rec)) for sensor_id, rec in self._state.items()]
        items.sort(key=lambda kv: (str(kv[1].origin), kv[0]))
        return items
