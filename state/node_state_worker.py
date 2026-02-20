# state/node_state_worker.py
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

		# LWW state:
		# global_sensor_id -> {value, ts_ms, origin, meta}
		# global_sensor_id = f"{origin}:{sensor_id}"
		self._state = {}

		# Updates for UI/observability (cleared on read)
		self._updates_ui = {}

		# Updates for replication (cleared on read)
		self._updates_replication = {}

	def run(self):
		while not self._stop_event.is_set():
			try:
				event = self.event_queue.get(timeout=1)
			except Empty:
				continue

			try:
				self._handle_sensor_event(event)
			except Exception:
				self.log.error("Failed to handle sensor event", exc_info=True)

	def merge_update(self, sensor_id, value, ts_ms, origin, meta=None):
		"""
		LWW merge for both local sensor ticks and remote network updates.
		Returns True if applied, False if stale.

		Keying:
		- state key is global per origin to avoid cross-node collisions:
		  global_sensor_id = f"{origin}:{sensor_id}"

		Tie-breaker:
		- if ts_ms is equal, origin lexical order wins.
		"""
		if meta is None:
			meta = {}

		if not isinstance(sensor_id, str) or sensor_id == "":
			return False
		if not isinstance(origin, str) or origin == "":
			return False
		if not isinstance(ts_ms, int):
			return False

		global_sensor_id = f"{origin}:{sensor_id}"

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
			prev = self._state.get(global_sensor_id)

			if prev is None:
				self._state[global_sensor_id] = update
				self._updates_ui[global_sensor_id] = update
				self._updates_replication[global_sensor_id] = update
				return True

			prev_ts = prev.get("ts_ms")
			prev_origin = prev.get("origin")

			if ts_ms > prev_ts:
				self._state[global_sensor_id] = update
				self._updates_ui[global_sensor_id] = update
				self._updates_replication[global_sensor_id] = update
				return True

			if ts_ms == prev_ts and origin > prev_origin:
				self._state[global_sensor_id] = update
				self._updates_ui[global_sensor_id] = update
				self._updates_replication[global_sensor_id] = update
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

	def _group_by_origin(self, flat_map):
		"""
		Convert:
			{ "A:s1": upd, "B:s2": upd }
		Into:
			{ "A": { "s1": upd }, "B": { "s2": upd } }

		If a key does not match "origin:sensor_id", it is grouped under self.node_id.
		"""
		grouped = {}

		for global_sensor_id, update in flat_map.items():
			origin = None
			sensor_id = None

			if isinstance(global_sensor_id, str) and ":" in global_sensor_id:
				origin, sensor_id = global_sensor_id.split(":", 1)

			if not origin:
				origin = self.node_id
			if not sensor_id:
				sensor_id = str(global_sensor_id)

			per_origin = grouped.get(origin)
			if per_origin is None:
				per_origin = {}
				grouped[origin] = per_origin

			per_origin[sensor_id] = update

		return grouped

	def get_state_snapshot(self):
		"""
		Returns full LWW state grouped by origin for the UI/API.

		Shape:
			{
				"nodeA": { "sensor_x": {...}, ... },
				"nodeB": { "sensor_y": {...}, ... }
			}
		"""
		with self._lock:
			return self._group_by_origin(deepcopy(self._state))

	def get_updates_snapshot(self):
		"""
		Returns updates since last call and clears UI buffer.
		Grouped by origin for the UI/API (same shape as get_state_snapshot()).
		"""
		with self._lock:
			snapshot = self._group_by_origin(deepcopy(self._updates_ui))
			self._updates_ui.clear()
			return snapshot

	def pop_replication_updates(self):
		"""
		Returns updates since last call and clears replication buffer.
		Used for Node->Node propagation.

		Shape kept as:
			{ self.node_id: { "origin:sensor_id": {...}, ... } }
		so the publisher can filter local-origin updates without changes.
		"""
		with self._lock:
			snapshot = {self.node_id: deepcopy(self._updates_replication)}
			self._updates_replication.clear()
			return snapshot

	def stop(self):
		self._stop_event.set()