"""Run the node-local worker that materializes replicated sensor state.

Responsibilities:
    - Consume normalized sensor events from the local producer queue.
    - Apply deterministic LWW merges for local samples and remote updates.
    - Expose full and incremental snapshots for UI polling and gossip publication.
    - Emit stable log output describing winning records and convergence decisions.
"""

import threading
import time
from queue import Empty
from typing import Any

from state.events import SensorEvent
from state.node_state_store import NodeStateStore, SensorMeta, SensorRecord


class NodeStateWorker(threading.Thread):
    """Maintain the node's replicated sensor register set in the background.

    Attributes:
        node_id (str): Local node identifier used as the origin for locally generated updates.
        event_queue (Any): Source queue supplying sensor events for local ingestion.
        log (Any): Logger-like object used for state and failure reporting.
        _stop_event (threading.Event): Shutdown signal checked by the worker loop.
        _store (NodeStateStore): Thread-safe LWW store and incremental snapshot buffers.
        _debug_dump_every_s (Any): Optional periodic dump cadence in seconds.
        _next_dump_ts (float | None): Monotonic deadline for the next periodic state dump.
    """

    def __init__(
        self,
        node_id: str,
        event_queue: Any,
        log: Any,
        debug_dump_every_s: Any = None,
    ) -> None:
        """Initialize the background worker and its LWW store.

        Args:
            node_id (str): Local node identifier for self-originated updates.
            event_queue (Any): Queue-like object supporting ``get(timeout=...)``.
            log (Any): Logger-like object supporting standard logging methods.
            debug_dump_every_s (Any): Optional positive interval for periodic full-state dumps.

        Returns:
            None: This constructor does not return a value.
        """
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

    def run(self) -> None:
        """Process queued sensor events until the worker is stopped.

        Returns:
            None: This method services the queue until shutdown.
        """
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

    def _maybe_log_periodic_dump(self) -> None:
        """Emit a periodic state dump when the configured deadline elapses.

        Returns:
            None: This method only updates logging state.
        """
        if self._next_dump_ts is None:
            return

        now = time.time()
        if now < self._next_dump_ts:
            return

        self.log_full_state(level="INFO")
        self._next_dump_ts = now + float(self._debug_dump_every_s)

    def _log_msg(self, level: str, msg: str) -> None:
        """Write one log message using the best available logger method.

        Args:
            level (str): Requested log level name.
            msg (str): Message body to emit.

        Returns:
            None: This method delegates emission to the logger-like object.
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

    def _format_record_line(self, sensor_id: str, rec: SensorRecord) -> str:
        """Format one winning record for deterministic state-dump logging.

        Args:
            sensor_id (str): Logical sensor identifier.
            rec (SensorRecord): Winning record to describe.

        Returns:
            str: Structured log line capturing the record winner and metadata.
        """
        return (
            f"sensor_id={sensor_id} "
            f"winner_origin={rec.origin} "
            f"ts_ms={rec.ts_ms} "
            f"value={rec.value} "
            f"unit={rec.meta.unit} "
            f"period_ms={rec.meta.period_ms}"
        )

    def dump_full_state(self) -> dict:
        """Expose a deterministic inspection view of the full register set.

        Returns:
            dict: Full state summary grouped by winning origin.
        """
        return self._store.dump_full_state()

    def log_full_state(self, level: str = "INFO") -> None:
        """Log the current register winners for debugging and convergence checks.

        Args:
            level (str): Requested logging level for the dump output.

        Returns:
            None: This method emits structured log lines only.
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

    def merge_update(
        self,
        sensor_id: str,
        value: Any,
        ts_ms: int,
        origin: str,
        meta: Any = None,
    ) -> bool:
        """Apply one local or remote sensor update under LWW ordering.

        Args:
            sensor_id (str): Logical sensor identifier shared across all origins.
            value (Any): Candidate sensor value.
            ts_ms (int): Candidate timestamp used as the primary LWW key.
            origin (str): Candidate origin used as the secondary LWW tie-break key.
            meta (Any): Optional metadata payload normalized into ``SensorMeta``.

        Returns:
            bool: ``True`` if the candidate becomes the new winner, else ``False``.
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
        """Delete one logical sensor from the underlying register set.

        Args:
            sensor_id (str): Logical sensor identifier to remove.

        Returns:
            bool: ``True`` if the sensor existed before removal.
        """
        return self._store.remove(sensor_id)

    def _handle_sensor_event(self, event: Any) -> None:
        """Normalize one local event and merge it as a self-originated update.

        Args:
            event (Any): Raw event accepted by ``SensorEvent.from_any``.

        Returns:
            None: This method updates replicated state in place.

        Raises:
            ValueError: If the supplied event cannot be normalized.
        """
        normalized_event = SensorEvent.from_any(event)

        self.merge_update(
            sensor_id=normalized_event.sensor_id,
            value=normalized_event.value,
            ts_ms=normalized_event.ts_ms,
            origin=self.node_id,
            meta=normalized_event.meta,
        )

    def get_state_snapshot(self) -> dict:
        """Return a full state snapshot shaped for the Web API and UI.

        Returns:
            dict: Full snapshot grouped by local node id and global sensor id.
        """
        return self._store.get_state_snapshot(node_id=self.node_id)

    def get_updates_snapshot(self) -> dict:
        """Drain updates intended for the Web API and UI consumer.

        Returns:
            dict: Incremental snapshot of records not yet read by the UI consumer.
        """
        return self._store.get_updates_snapshot(node_id=self.node_id)

    def pop_replication_updates(self) -> dict:
        """Drain updates intended for best-effort replication gossip.

        Returns:
            dict: Incremental snapshot of records not yet read by the publisher thread.
        """
        return self._store.pop_replication_updates(node_id=self.node_id)

    def stop(self) -> None:
        """Request graceful worker termination.

        Returns:
            None: This method only signals shutdown.
        """
        self._stop_event.set()
