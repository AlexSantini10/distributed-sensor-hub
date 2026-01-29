import random
from sensors.base_sensor import BaseSensor


class TrendSensor(BaseSensor):
	def __init__(
		self,
		sensor_id,
		start,
		slope,
		noise,
		period_ms,
		callback=None,
		unit=None,
	):
		super().__init__(
			sensor_id,
			period_ms,
			callback,
			unit=unit,
		)
		self.value = start
		self.slope = slope
		self.noise = noise

	def generate_value(self):
		self.value += self.slope
		self.value += random.uniform(-self.noise, self.noise)
		return self.value
