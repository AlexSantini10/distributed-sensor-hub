import os

from sensors.numeric_sensor import NumericSensor
from sensors.boolean_sensor import BooleanSensor
from sensors.categorical_sensor import CategoricalSensor
from sensors.incremental_sensor import IncrementalSensor
from sensors.trend_sensor import TrendSensor
from sensors.spike_sensor import SpikeSensor
from sensors.wave_sensor import WaveSensor
from sensors.noise_sensor import NoiseSensor


class SensorManager:
	"""
	Loads and manages sensors based on environment configuration.
	Each sensor emits structured events through the provided callback.
	"""

	def __init__(self, callback):
		self.callback = callback
		self.sensors = []

	def load_from_env(self):
		if self.sensors:
			raise RuntimeError("Sensors already loaded")

		try:
			count = int(os.getenv("SENSORS", "0"))
		except ValueError:
			raise ValueError("SENSORS must be an integer")

		for i in range(count):
			prefix = f"SENSOR_{i}_"

			s_type = os.getenv(prefix + "TYPE")
			if not s_type:
				raise ValueError(f"Missing {prefix}TYPE")

			period_ms = int(os.getenv(prefix + "PERIOD_MS", "0"))
			if period_ms <= 0:
				raise ValueError(f"Invalid {prefix}PERIOD_MS")

			name = os.getenv(prefix + "NAME", f"sensor_{i}")
			sensor_id = f"{name}@{i}"

			# OPTIONAL METADATA
			unit = os.getenv(prefix + "UNIT")

			# NUMERIC
			if s_type == "numeric":
				min_val = float(os.getenv(prefix + "MIN"))
				max_val = float(os.getenv(prefix + "MAX"))

				sensor = NumericSensor(
					sensor_id,
					min_val,
					max_val,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# BOOLEAN
			elif s_type == "boolean":
				p_true = float(os.getenv(prefix + "P_TRUE", 0.5))

				sensor = BooleanSensor(
					sensor_id,
					p_true,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# CATEGORICAL
			elif s_type == "categorical":
				values = [
					v.strip()
					for v in os.getenv(prefix + "VALUES", "").split(",")
					if v.strip()
				]
				if not values:
					raise ValueError(f"{prefix}VALUES must not be empty")

				sensor = CategoricalSensor(
					sensor_id,
					values,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# INCREMENTAL
			elif s_type == "incremental":
				start = float(os.getenv(prefix + "START", 0))
				step_pct = float(os.getenv(prefix + "STEP_PCT", 1))

				sensor = IncrementalSensor(
					sensor_id,
					start,
					step_pct,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# TREND
			elif s_type == "trend":
				start = float(os.getenv(prefix + "START", 0))
				slope = float(os.getenv(prefix + "SLOPE", 0.1))
				noise = float(os.getenv(prefix + "NOISE", 0.0))

				sensor = TrendSensor(
					sensor_id,
					start,
					slope,
					noise,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# SPIKE
			elif s_type == "spike":
				baseline = float(os.getenv(prefix + "BASELINE", 0))
				spike_height = float(os.getenv(prefix + "SPIKE_HEIGHT", 10))
				p_spike = float(os.getenv(prefix + "P_SPIKE", 0.2))

				sensor = SpikeSensor(
					sensor_id,
					baseline,
					spike_height,
					p_spike,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# WAVE
			elif s_type == "wave":
				amplitude = float(os.getenv(prefix + "AMPLITUDE", 1))
				frequency = float(os.getenv(prefix + "FREQUENCY", 1))

				sensor = WaveSensor(
					sensor_id,
					amplitude,
					frequency,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			# NOISE
			elif s_type == "noise":
				base = float(os.getenv(prefix + "BASE", 0))
				noise = float(os.getenv(prefix + "NOISE", 1))

				sensor = NoiseSensor(
					sensor_id,
					base,
					noise,
					period_ms,
					callback=self.callback,
					unit=unit,
				)

			else:
				raise ValueError(f"Unsupported sensor type: {s_type}")

			self.sensors.append(sensor)

	def start_all(self):
		for s in self.sensors:
			s.start()

	def stop_all(self):
		for s in self.sensors:
			s.stop()
