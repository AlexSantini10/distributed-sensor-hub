import random
from sensors.base_sensor import BaseSensor

class NumericSensor(BaseSensor):
	def __init__(self, sensor_id, min_val, max_val, period_ms, unit=None, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.min_val = min_val
		self.max_val = max_val
		self.unit = unit

	def generate_value(self):
		return random.uniform(self.min_val, self.max_val)
