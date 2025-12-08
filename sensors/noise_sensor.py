import random
from sensors.base_sensor import BaseSensor

class NoiseSensor(BaseSensor):
	def __init__(self, sensor_id, base, noise, period_ms, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.base = base
		self.noise = noise

	def generate_value(self):
		return self.base + random.uniform(-self.noise, self.noise)
