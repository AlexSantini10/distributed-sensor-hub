# sensors/base_sensor.py
import threading
import time


class BaseSensor:
	def __init__(self, sensor_id, period_ms, callback):
		self.sensor_id = sensor_id
		self.period_ms = period_ms
		self.callback = callback

		self._stop_event = threading.Event()
		self._thread = None

	def generate_value(self):
		raise NotImplementedError

	def _loop(self):
		next_deadline = time.monotonic()
		period_s = self.period_ms / 1000.0

		while not self._stop_event.is_set():
			value = self.generate_value()
			ts_ms = int(time.time() * 1000)

			self.callback({
				"sensor_id": self.sensor_id,
				"value": value,
				"ts_ms": ts_ms,
			})

			next_deadline += period_s
			sleep_time = next_deadline - time.monotonic()
			if sleep_time > 0:
				self._stop_event.wait(timeout=sleep_time)

	def start(self):
		if self._thread is not None:
			return
		self._thread = threading.Thread(target=self._loop, daemon=True)
		self._thread.start()

	def stop(self):
		self._stop_event.set()
		if self._thread:
			self._thread.join(timeout=2)
