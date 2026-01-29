import random
from sensors.base_sensor import BaseSensor


class BooleanSensor(BaseSensor):
	def __init__(self, sensor_id, p_true, period_ms, callback, *, unit=None):
		super().__init__(
			sensor_id=sensor_id,
			period_ms=period_ms,
			callback=callback,
			unit=unit,
		)
		self.p_true = p_true

	def generate_value(self):
		return random.random() < self.p_true
