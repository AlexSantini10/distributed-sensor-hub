import random
from sensors.base_sensor import BaseSensor

class BooleanSensor(BaseSensor):
	def __init__(self, sensor_id, p_true, period_ms, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.p_true = p_true

	def generate_value(self):
		return random.random() < self.p_true
