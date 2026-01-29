import math
import time
from sensors.base_sensor import BaseSensor


class WaveSensor(BaseSensor):
	def __init__(
		self,
		sensor_id,
		amplitude,
		frequency,
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
		self.amplitude = amplitude
		self.frequency = frequency
		self.start_time = time.time()

	def generate_value(self):
		t = time.time() - self.start_time
		return self.amplitude * math.sin(2 * math.pi * self.frequency * t)
