import random
from sensors.base_sensor import BaseSensor


class NumericSensor(BaseSensor):
	def __init__(
		self,
		sensor_id,
		min_val,
		max_val,
		period_ms,
		callback,
		*,
		unit=None,
	):
		min_val = float(min_val)
		max_val = float(max_val)

		if min_val >= max_val:
			raise ValueError(
				f"min_val must be < max_val (got {min_val} >= {max_val})"
			)

		super().__init__(
			sensor_id=sensor_id,
			period_ms=period_ms,
			callback=callback,
			unit=unit,
		)

		self.min_val = min_val
		self.max_val = max_val

	def generate_value(self):
		return random.uniform(self.min_val, self.max_val)
