# state/node_state_worker.py
"""
Node state worker with LWW (last-writer-wins) semantics.

Internal state is keyed by sensor_id to ensure updates from different origins
compete for the same logical sensor. Conflict resolution uses (ts_ms, origin)
with origin as tie-breaker (lexicographically larger origin wins).

Snapshots are grouped by local node_id for UI/API compatibility with tests.
Each sensor entry is exposed with a global key "origin:sensor_id".
"""

import threading
import time
from queue import Empty

from state.events import SensorEvent
from state.node_state_store import NodeStateStore, SensorMeta, SensorRecord


class NodeStateWorker(threading.Thread):
    """
    Background worker responsible for ingesting local sensor events and
    maintaining a replicated LWW state.

    Public API:
    - merge_update(): apply a local or remote update with LWW merge
    - get_state_snapshot(): full state for UI/API
    - get_updates_snapshot(): incremental updates for UI/API
    - pop_replication_updates(): incremental updates for replication
    - dump_full_state(): inspection-friendly full state view
    - log_full_state(): log a full state dump for debugging
    """

    def __init__(self, node_id, event_queue, log, debug_dump_every_s=None):
        super().__init__(daemon=True)

        self.node_id = node_id
        self.event_queue = event_queue
        self.log = log

        self._stop_event = threading.Event()
        self._store = NodeStateStore()

        self._debug_dump_every_s = debug_dump_every_s
        self._next_dump_ts = (
            time.time() + debug_dump_every_s
            if isinstance(debug_dump_every_s, (int, float)) and debug_dump_every_s > 0
            else None
        )

    def run(self):
        while not self._stop_event.is_set():
            self._maybe_log_periodic_dump()

            try:
                event = self.event_queue.get(timeout=1)
            except Empty:
                continue

            try:
                self._handle_sensor_event(event)
            except Exception:
                self.log.error("Failed to handle sensor event", exc_info=True)

    def _maybe_log_periodic_dump(self):
        if self._next_dump_ts is None:
            return

        now = time.time()
        if now < self._next_dump_ts:
            return

        self.log_full_state(level="INFO")
        self._next_dump_ts = now + float(self._debug_dump_every_s)

    def _log_msg(self, level, msg):
        """
        Safe logger wrapper.

        Some tests inject a DummyLog without debug(); fall back to info().
        """
        if self.log is None:
            return

        method = getattr(self.log, level, None)
        if callable(method):
            method(msg)
            return

        if level == "debug":
            method = getattr(self.log, "info", None)
            if callable(method):
                method(msg)

    def _format_record_line(self, sensor_id, rec: SensorRecord):
        return (
            f"sensor_id={sensor_id} "
            f"winner_origin={rec.origin} "
            f"ts_ms={rec.ts_ms} "
            f"value={rec.value} "
            f"unit={rec.meta.unit} "
            f"period_ms={rec.meta.period_ms}"
        )

    def dump_full_state(self):
        return self._store.dump_full_state()

    def log_full_state(self, level="INFO"):
        """
        Log a full-state dump to help verify association (sensor -> origin).

        level:
        - "DEBUG", "INFO", "WARNING", "ERROR"
        """
        items = self._store.get_items_for_logging()

        count_by_origin = {}
        for sensor_id, rec in items:
            origin = rec.origin
            if not isinstance(origin, str) or origin == "":
                origin = "UNKNOWN"
            count_by_origin[origin] = count_by_origin.get(origin, 0) + 1

        header = (
            f"FULL_STATE_DUMP node={self.node_id} "
            f"total={len(items)} "
            f"by_origin={dict(sorted(count_by_origin.items(), key=lambda kv: kv[0]))}"
        )

        level_lc = str(level).lower()
        if level_lc not in {"debug", "info", "warning", "error"}:
            level_lc = "info"

        self._log_msg(level_lc, header)
        for sensor_id, rec in items:
            self._log_msg(level_lc, self._format_record_line(sensor_id, rec))

    def merge_update(self, sensor_id, value, ts_ms, origin, meta=None):
        """
        LWW merge for both local sensor ticks and remote network updates.

        Resolution:
        - newer ts_ms wins
        - on ts_ms tie, lexicographically larger origin wins

        Returns:
        - True if applied
        - False if stale/invalid
        """
        if meta is None:
            meta = {}

        if not isinstance(sensor_id, str) or sensor_id == "":
            return False
        if not isinstance(origin, str) or origin == "":
            return False
        if not isinstance(ts_ms, int):
            return False

        update = SensorRecord(
            value=value,
            ts_ms=ts_ms,
            origin=origin,
            meta=SensorMeta.from_dict(meta),
        )

        applied, reason, previous = self._store.merge_lww(sensor_id=sensor_id, update=update)

        if applied and reason == "insert":
            self._log_msg(
                "info",
                f"LWW applied (insert): sensor={sensor_id} origin={origin} "
                f"ts={ts_ms} value={value} unit={update.meta.unit} "
                f"period_ms={update.meta.period_ms}",
            )
            self._log_msg("info", self._format_record_line(sensor_id, update))
            return True

        if applied and reason == "newer_ts":
            self._log_msg(
                "info",
                f"LWW applied (newer_ts): sensor={sensor_id} origin={origin} "
                f"ts={ts_ms} value={value} prev_origin={previous.origin} prev_ts={previous.ts_ms}",
            )
            self._log_msg("info", self._format_record_line(sensor_id, update))
            return True

        if applied and reason == "tie_break":
            self._log_msg(
                "info",
                f"LWW applied (tie_break): sensor={sensor_id} origin={origin} "
                f"ts={ts_ms} value={value} prev_origin={previous.origin} prev_ts={previous.ts_ms}",
            )
            self._log_msg("info", self._format_record_line(sensor_id, update))
            return True

        self._log_msg(
            "debug",
            f"LWW ignored (stale): sensor={sensor_id} origin={origin} "
            f"ts={ts_ms} value={value} prev_origin={previous.origin} prev_ts={previous.ts_ms}",
        )
        self._log_msg("debug", self._format_record_line(sensor_id, previous))
        return False

    def remove_sensor(self, sensor_id: str) -> bool:
        """Remove sensor record from the underlying store."""
        return self._store.remove(sensor_id)

    def _handle_sensor_event(self, event):
        normalized_event = SensorEvent.from_any(event)

        self.merge_update(
            sensor_id=normalized_event.sensor_id,
            value=normalized_event.value,
            ts_ms=normalized_event.ts_ms,
            origin=self.node_id,
            meta=normalized_event.meta,
        )

    def get_state_snapshot(self):
        return self._store.get_state_snapshot(node_id=self.node_id)

    def get_updates_snapshot(self):
        return self._store.get_updates_snapshot(node_id=self.node_id)

    def pop_replication_updates(self):
        return self._store.pop_replication_updates(node_id=self.node_id)

    def stop(self):
        """Request thread termination."""
        self._stop_event.set()
