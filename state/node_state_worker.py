import threading
from queue import Empty


class NodeStateWorker(threading.Thread):
	def __init__(self, node_id, event_queue, log):
		super().__init__(daemon=True)
		self.node_id = node_id
		self.event_queue = event_queue
		self.log = log

		self._stop_event = threading.Event()
		self._lock = threading.Lock()

		self.state = {}

	def run(self):
		while not self._stop_event.is_set():
			try:
				event = self.event_queue.get(timeout=1)
			except Empty:
				continue

			self._handle_sensor_event(event)

	def _handle_sensor_event(self, event):
		sensor_id = event["sensor_id"]
		value = event["value"]
		ts_ms = event["ts_ms"]

		update = {
			"value": value,
			"ts_ms": ts_ms,
			"origin": self.node_id,
		}

		with self._lock:
			prev = self.state.get(sensor_id)
			if prev is None or ts_ms > prev["ts_ms"]:
				self.state[sensor_id] = update

				self.log.info(
					f"LWW update applied: "
					f"sensor={sensor_id} value={value} ts={ts_ms}"
				)

	def get_state_snapshot(self):
		with self._lock:
			return dict(self.state)

	def stop(self):
		self._stop_event.set()
