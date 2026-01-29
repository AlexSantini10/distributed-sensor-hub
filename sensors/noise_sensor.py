import random
from sensors.base_sensor import BaseSensor


class NoiseSensor(BaseSensor):
	def __init__(
		self,
		sensor_id,
		base,
		noise,
		period_ms,
		callback,
		*,
		unit=None,
	):
		if noise < 0:
			raise ValueError("noise must be >= 0")

		super().__init__(
			sensor_id=sensor_id,
			period_ms=period_ms,
			callback=callback,
			unit=unit,
		)

		self.base = float(base)
		self.noise = float(noise)

	def generate_value(self):
		return self.base + random.uniform(-self.noise, self.noise)
