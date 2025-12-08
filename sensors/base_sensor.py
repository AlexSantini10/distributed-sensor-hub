import threading
import time

class BaseSensor:
	def __init__(self, sensor_id, period_ms, callback=None):
		self.sensor_id = sensor_id				# unique sensor identifier
		self.period_ms = period_ms				# generation interval
		self.callback = callback				# function to send output
		self._running = False
		self._thread = None

	def generate_value(self):
		raise NotImplementedError("Subclasses must implement generate_value()")

	def _loop(self):
		while self._running: 
			value = self.generate_value()
			ts = int(time.time() * 1000)

			if self.callback:
				self.callback(self.sensor_id, value, ts)

			time.sleep(self.period_ms / 1000.0)



	def start(self):
		if self._running:
			return
		self._running = True
		self._thread = threading.Thread(target=self._loop, daemon=True)
		self._thread.start()

	def stop(self):
		self._running = False
		if self._thread:
			self._thread.join(timeout=1)
