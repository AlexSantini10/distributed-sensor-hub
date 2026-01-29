import random
from sensors.base_sensor import BaseSensor


class CategoricalSensor(BaseSensor):
	def __init__(self, sensor_id, categories, period_ms, callback, *, unit=None):
		if not categories:
			raise ValueError("CategoricalSensor requires at least one category")

		super().__init__(
			sensor_id=sensor_id,
			period_ms=period_ms,
			callback=callback,
			unit=unit,
		)
		self.categories = list(categories)

	def generate_value(self):
		return random.choice(self.categories)
