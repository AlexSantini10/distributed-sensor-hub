import random
from sensors.base_sensor import BaseSensor


class IncrementalSensor(BaseSensor):
	def __init__(
		self,
		sensor_id,
		start,
		step_pct,
		period_ms,
		callback,
		*,
		unit=None,
	):
		if step_pct < 0:
			raise ValueError("step_pct must be >= 0")

		super().__init__(
			sensor_id=sensor_id,
			period_ms=period_ms,
			callback=callback,
			unit=unit,
		)

		self.value = float(start)
		self.step_pct = float(step_pct)

	def generate_value(self):
		# step_pct = 10 -> +/-10% of current value
		delta = abs(self.value) * (self.step_pct / 100.0)

		if delta > 0:
			self.value += random.uniform(-delta, delta)

		return self.value
