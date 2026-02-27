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
from copy import deepcopy


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
		self._lock = threading.Lock()

		# LWW state:
		# sensor_id -> {value, ts_ms, origin, meta}
		self._state = {}

		# Updates for UI/observability (cleared on read)
		# sensor_id -> record
		self._updates_ui = {}

		# Updates for replication (cleared on read)
		# sensor_id -> record
		self._updates_replication = {}

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

	def _normalize_meta(self, meta):
		if not isinstance(meta, dict):
			meta = {}
		return {
			"unit": meta.get("unit"),
			"period_ms": meta.get("period_ms"),
		}

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

	def _format_record_line(self, sensor_id, rec):
		meta = rec.get("meta") or {}
		return (
			f"sensor_id={sensor_id} "
			f"winner_origin={rec.get('origin')} "
			f"ts_ms={rec.get('ts_ms')} "
			f"value={rec.get('value')} "
			f"unit={meta.get('unit')} "
			f"period_ms={meta.get('period_ms')}"
		)

	def dump_full_state(self):
		"""
		Return a deterministic, inspection-friendly view of the full state.

		Returns:
			{
				"by_origin": {
					"node-3": {
						"count": 3,
						"sensors": [
							{"sensor_id": "...", "ts_ms": ..., "value": ..., "unit": ..., "period_ms": ...},
							...
						]
					},
					...
				},
				"total": <int>
			}
		"""
		with self._lock:
			state_copy = deepcopy(self._state)

		by_origin = {}
		for sensor_id, rec in state_copy.items():
			origin = rec.get("origin")
			if not isinstance(origin, str) or origin == "":
				origin = "UNKNOWN"

			meta = rec.get("meta") or {}
			item = {
				"sensor_id": sensor_id,
				"ts_ms": rec.get("ts_ms"),
				"value": rec.get("value"),
				"unit": meta.get("unit"),
				"period_ms": meta.get("period_ms"),
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

	def log_full_state(self, level="INFO"):
		"""
		Log a full-state dump to help verify association (sensor -> origin).

		level:
		- "DEBUG", "INFO", "WARNING", "ERROR"
		"""
		with self._lock:
			items = list(self._state.items())

		items.sort(key=lambda kv: (str(kv[1].get("origin")), kv[0]))

		count_by_origin = {}
		for sensor_id, rec in items:
			origin = rec.get("origin")
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

		update = {
			"value": value,
			"ts_ms": ts_ms,
			"origin": origin,
			"meta": self._normalize_meta(meta),
		}

		with self._lock:
			prev = self._state.get(sensor_id)
			if prev is None:
				self._state[sensor_id] = update
				self._updates_ui[sensor_id] = update
				self._updates_replication[sensor_id] = update

				self._log_msg(
					"info",
					f"LWW applied (insert): sensor={sensor_id} origin={origin} "
					f"ts={ts_ms} value={value} unit={update['meta'].get('unit')} "
					f"period_ms={update['meta'].get('period_ms')}",
				)
				self._log_msg("info", self._format_record_line(sensor_id, update))
				return True

			prev_ts = prev.get("ts_ms")
			prev_origin = prev.get("origin")

			if ts_ms > prev_ts:
				self._state[sensor_id] = update
				self._updates_ui[sensor_id] = update
				self._updates_replication[sensor_id] = update

				self._log_msg(
					"info",
					f"LWW applied (newer_ts): sensor={sensor_id} origin={origin} "
					f"ts={ts_ms} value={value} prev_origin={prev_origin} prev_ts={prev_ts}",
				)
				self._log_msg("info", self._format_record_line(sensor_id, update))
				return True

			if ts_ms == prev_ts and origin > prev_origin:
				self._state[sensor_id] = update
				self._updates_ui[sensor_id] = update
				self._updates_replication[sensor_id] = update

				self._log_msg(
					"info",
					f"LWW applied (tie_break): sensor={sensor_id} origin={origin} "
					f"ts={ts_ms} value={value} prev_origin={prev_origin} prev_ts={prev_ts}",
				)
				self._log_msg("info", self._format_record_line(sensor_id, update))
				return True

			self._log_msg(
				"debug",
				f"LWW ignored (stale): sensor={sensor_id} origin={origin} "
				f"ts={ts_ms} value={value} prev_origin={prev_origin} prev_ts={prev_ts}",
			)
			self._log_msg("debug", self._format_record_line(sensor_id, prev))
			return False

	def _handle_sensor_event(self, event):
		sensor_id = event["sensor_id"]
		value = event["value"]
		ts_ms = event["ts_ms"]
		meta = event.get("meta", {})

		self.merge_update(
			sensor_id=sensor_id,
			value=value,
			ts_ms=ts_ms,
			origin=self.node_id,
			meta=meta,
		)

	def _snapshot_grouped_for_ui(self, state_map):
		"""
		Render internal {sensor_id: record} to the UI/API shape expected
		by tests: { self.node_id: { "origin:sensor_id": record, ... } }.
		"""
		per_node = {}
		for sensor_id, record in state_map.items():
			origin = record.get("origin")
			if not isinstance(origin, str) or origin == "":
				origin = self.node_id
			global_sensor_id = f"{origin}:{sensor_id}"
			per_node[global_sensor_id] = record
		return {self.node_id: per_node}

	def get_state_snapshot(self):
		with self._lock:
			return self._snapshot_grouped_for_ui(deepcopy(self._state))

	def get_updates_snapshot(self):
		with self._lock:
			snapshot = self._snapshot_grouped_for_ui(deepcopy(self._updates_ui))
			self._updates_ui.clear()
			return snapshot

	def pop_replication_updates(self):
		with self._lock:
			per_node = {}
			for sensor_id, record in self._updates_replication.items():
				origin = record.get("origin")
				if not isinstance(origin, str) or origin == "":
					origin = self.node_id
				global_sensor_id = f"{origin}:{sensor_id}"
				per_node[global_sensor_id] = deepcopy(record)

			self._updates_replication.clear()
			return {self.node_id: per_node}

	def stop(self):
		"""Request thread termination."""
		self._stop_event.set()