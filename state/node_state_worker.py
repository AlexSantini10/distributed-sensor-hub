import threading
from queue import Empty
from copy import deepcopy


class NodeStateWorker(threading.Thread):
	def __init__(self, node_id, event_queue, log):
		super().__init__(daemon=True)

		self.node_id = node_id
		self.event_queue = event_queue
		self.log = log

		self._stop_event = threading.Event()
		self._lock = threading.Lock()

		# LWW state: sensor_id -> {value, ts_ms, origin, meta}
		self._state = {}

		# Volatile updates since last read
		self._updates = {}

	def run(self):
		while not self._stop_event.is_set():
			try:
				event = self.event_queue.get(timeout=1)
			except Empty:
				continue

			try:
				self._handle_sensor_event(event)
			except Exception:
				self.log.error(
					"Failed to handle sensor event",
					exc_info=True,
				)

	def merge_update(self, sensor_id, value, ts_ms, origin, meta=None):
		"""
		LWW merge for both local sensor ticks and remote network updates.
		Returns True if applied, False if stale.

		Tie-breaker: if ts_ms is equal, origin lexical order wins.
		"""
		if meta is None:
			meta = {}

		update = {
			"value": value,
			"ts_ms": ts_ms,
			"origin": origin,
			"meta": {
				"unit": meta.get("unit"),
				"period_ms": meta.get("period_ms"),
			},
		}

		with self._lock:
			prev = self._state.get(sensor_id)

			if prev is None:
				self._state[sensor_id] = update
				self._updates[sensor_id] = update
				return True

			prev_ts = prev.get("ts_ms")
			prev_origin = prev.get("origin")

			if ts_ms > prev_ts:
				self._state[sensor_id] = update
				self._updates[sensor_id] = update
				return True

			if ts_ms == prev_ts and origin > prev_origin:
				self._state[sensor_id] = update
				self._updates[sensor_id] = update
				return True

			return False

	def _handle_sensor_event(self, event):
		sensor_id = event["sensor_id"]
		value = event["value"]
		ts_ms = event["ts_ms"]
		meta = event.get("meta", {})

		applied = self.merge_update(
			sensor_id=sensor_id,
			value=value,
			ts_ms=ts_ms,
			origin=self.node_id,
			meta=meta,
		)

		if applied:
			self.log.info(
				f"LWW update applied: "
				f"sensor={sensor_id} value={value} "
				f"unit={meta.get('unit')} ts={ts_ms}"
			)

	def get_state_snapshot(self):
		"""
		Returns full LWW state.
		Structured for multi-node future.
		"""
		with self._lock:
			return {
				self.node_id: deepcopy(self._state)
			}

	def get_updates_snapshot(self):
		"""
		Returns updates since last call and clears buffer.
		Used for UI / gossip / observability.
		"""
		with self._lock:
			snapshot = {
				self.node_id: deepcopy(self._updates)
			}
			self._updates.clear()
			return snapshot

	def stop(self):
		self._stop_event.set()
