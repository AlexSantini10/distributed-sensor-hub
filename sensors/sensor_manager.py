"""Define sensor loading and lifecycle orchestration from environment state.

Responsibilities:
    Translate environment configuration into concrete sensor instances, enforce
    configuration invariants, and coordinate the set of local publishers whose
    messages feed the distributed event pipeline.
"""

import os
from collections.abc import Callable
from typing import Any

from sensors.boolean_sensor import BooleanSensor
from sensors.categorical_sensor import CategoricalSensor
from sensors.incremental_sensor import IncrementalSensor
from sensors.noise_sensor import NoiseSensor
from sensors.numeric_sensor import NumericSensor
from sensors.spike_sensor import SpikeSensor
from sensors.trend_sensor import TrendSensor
from sensors.wave_sensor import WaveSensor


class SensorManager:
    """Represent environment-driven ownership of local sensor publishers.

    Attributes:
        callback (Callable[[dict[str, Any]], None]): Shared sink that receives
            every sensor message emitted by managed sensors.
        sensors (list[NumericSensor | BooleanSensor | CategoricalSensor | IncrementalSensor | TrendSensor | SpikeSensor | WaveSensor | NoiseSensor]): Loaded sensor instances that belong to this runtime.
    """

    def __init__(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Initialize the manager with a shared message sink.

        Args:
            callback (Callable[[dict[str, Any]], None]): Consumer invoked by all
                managed sensors for emitted messages.

        Returns:
            None (None): This constructor initializes the manager instance.
        """
        self.callback = callback
        self.sensors = []

    def load_from_env(self) -> None:
        """Load sensor instances from process environment variables.

        Sensor identifiers are derived as `{name}@{index}` and are assumed to
        remain stable for the life of the process. The emitted message format is
        inherited from each sensor, so downstream gossip or LWW merge logic can
        treat all configured sensors uniformly regardless of concrete type.

        Args:
            None (None): This method reads process environment variables only.

        Returns:
            None (None): This method populates `sensors` in declaration order.

        Raises:
            RuntimeError: Raised when sensors have already been loaded.
            ValueError: Raised when required configuration is missing or
                invalid.
        """
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

            unit = os.getenv(prefix + "UNIT")

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

            elif s_type == "boolean":
                p_true = float(os.getenv(prefix + "P_TRUE", 0.5))

                sensor = BooleanSensor(
                    sensor_id,
                    p_true,
                    period_ms,
                    callback=self.callback,
                    unit=unit,
                )

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

    def start_all(self) -> None:
        """Start every loaded sensor publisher.

        Args:
            None (None): This method operates on loaded sensors only.

        Returns:
            None (None): This method starts each managed sensor in order.
        """
        for s in self.sensors:
            s.start()

    def stop_all(self) -> None:
        """Stop every loaded sensor publisher.

        Args:
            None (None): This method operates on loaded sensors only.

        Returns:
            None (None): This method stops each managed sensor in order.
        """
        for s in self.sensors:
            s.stop()
