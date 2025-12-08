import random
from sensors.base_sensor import BaseSensor

class CategoricalSensor(BaseSensor):
	def __init__(self, sensor_id, categories, period_ms, callback=None):
		super().__init__(sensor_id, period_ms, callback)
		self.categories = categories

	def generate_value(self):
		return random.choice(self.categories)
