import random
from sensors.base_sensor import BaseSensor

class IncrementalSensor(BaseSensor):
	def __init__(self, sensor_id, start, step_pct, period_ms, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.value = start
		self.step_pct = step_pct

	def generate_value(self):
		# Example: step_pct = 10 means ±10% variation
		change = self.value * (self.step_pct / 100.0)
		self.value += random.uniform(-change, change)
		return self.value
