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
    Each sensor pushes values asynchronously through the provided callback.
    """

    def __init__(self, callback):
        self.callback = callback       # function(sensor_id, value, timestamp)
        self.sensors = []              # list of BaseSensor instances

    def load_from_env(self):
        """
        Parses SENSOR_i_* variables and instantiates the correct sensor type.
        Required: SENSOR_i_TYPE, SENSOR_i_PERIOD_MS
        Additional fields depend on sensor type.
        """

        count = int(os.getenv("SENSORS", 0))

        for i in range(count):
            prefix = f"SENSOR_{i}_"

            s_type = os.getenv(prefix + "TYPE")
            if s_type is None:
                raise ValueError(f"Missing {prefix}TYPE")

            name = os.getenv(prefix + "NAME", f"sensor_{i}")
            period_ms = int(os.getenv(prefix + "PERIOD_MS"))

            sensor_id = name

            # NUMERIC SENSOR --------------------------------------------
            if s_type == "numeric":
                min_val = float(os.getenv(prefix + "MIN"))
                max_val = float(os.getenv(prefix + "MAX"))
                unit = os.getenv(prefix + "UNIT", None)
                sensor = NumericSensor(sensor_id, min_val, max_val, period_ms, unit, self.callback)

            # BOOLEAN SENSOR --------------------------------------------
            elif s_type == "boolean":
                p_true = float(os.getenv(prefix + "P_TRUE", 0.5))
                sensor = BooleanSensor(sensor_id, p_true, period_ms, self.callback)

            # CATEGORICAL SENSOR ----------------------------------------
            elif s_type == "categorical":
                values = os.getenv(prefix + "VALUES", "")
                values = [v.strip() for v in values.split(",") if v.strip()]
                if not values:
                    raise ValueError(f"{prefix}VALUES must contain at least one category")
                sensor = CategoricalSensor(sensor_id, values, period_ms, self.callback)

            # INCREMENTAL SENSOR ----------------------------------------
            elif s_type == "incremental":
                start = float(os.getenv(prefix + "START", 0))
                step_pct = float(os.getenv(prefix + "STEP_PCT", 1))
                sensor = IncrementalSensor(sensor_id, start, step_pct, period_ms, self.callback)

            # TREND SENSOR ----------------------------------------------
            elif s_type == "trend":
                start = float(os.getenv(prefix + "START", 0))
                slope = float(os.getenv(prefix + "SLOPE", 0.1))
                noise = float(os.getenv(prefix + "NOISE", 0.0))
                sensor = TrendSensor(sensor_id, start, slope, noise, period_ms, self.callback)

            # SPIKE SENSOR ----------------------------------------------
            elif s_type == "spike":
                baseline = float(os.getenv(prefix + "BASELINE", 0))
                spike_height = float(os.getenv(prefix + "SPIKE_HEIGHT", 10))
                p_spike = float(os.getenv(prefix + "P_SPIKE", 0.2))
                sensor = SpikeSensor(sensor_id, baseline, spike_height, p_spike, period_ms, self.callback)

            # WAVE SENSOR -----------------------------------------------
            elif s_type == "wave":
                amplitude = float(os.getenv(prefix + "AMPLITUDE", 1))
                frequency = float(os.getenv(prefix + "FREQUENCY", 1))
                sensor = WaveSensor(sensor_id, amplitude, frequency, period_ms, self.callback)

            # NOISE SENSOR -----------------------------------------------
            elif s_type == "noise":
                base = float(os.getenv(prefix + "BASE", 0))
                noise = float(os.getenv(prefix + "NOISE", 1))
                sensor = NoiseSensor(sensor_id, base, noise, period_ms, self.callback)

            else:
                raise ValueError(f"Unsupported sensor type: {s_type}")

            self.sensors.append(sensor)

    def start_all(self):
        """Starts all sensors concurrently."""
        for s in self.sensors:
            s.start()

    def stop_all(self):
        """Stops all sensors and waits for threads to terminate."""
        for s in self.sensors:
            s.stop()
