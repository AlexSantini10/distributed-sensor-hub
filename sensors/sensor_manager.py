"""Define sensor loading and lifecycle orchestration from configuration state.

Responsibilities:
    Translate validated sensor configuration into concrete sensor instances,
    enforce initialization invariants, and coordinate the set of local
    publishers whose messages feed the distributed event pipeline.
"""

from sensors.boolean_sensor import BooleanSensor
from sensors.categorical_sensor import CategoricalSensor
from sensors.incremental_sensor import IncrementalSensor
from sensors.noise_sensor import NoiseSensor
from sensors.numeric_sensor import NumericSensor
from sensors.spike_sensor import SpikeSensor
from sensors.trend_sensor import TrendSensor
from sensors.wave_sensor import WaveSensor
from utils.config import SensorConfig, SensorType
from utils.typing import SensorCallback


SensorInstance = (
    NumericSensor
    | BooleanSensor
    | CategoricalSensor
    | IncrementalSensor
    | TrendSensor
    | SpikeSensor
    | WaveSensor
    | NoiseSensor
)


class SensorManager:
    """Represent configuration-driven ownership of local sensor publishers.

    Attributes:
        callback (SensorCallback): Shared sink that receives
            every sensor message emitted by managed sensors.
        sensors (list[SensorInstance]): Loaded sensor instances that belong to this runtime.
    """

    def __init__(self, callback: SensorCallback) -> None:
        """Initialize the manager with a shared message sink.

        Args:
            callback (SensorCallback): Consumer invoked by all
                managed sensors for emitted messages.

        Returns:
            None (None): This constructor initializes the manager instance.
        """
        self.callback = callback
        self.sensors: list[SensorInstance] = []

    def load(self, sensor_configs: tuple[SensorConfig, ...]) -> None:
        """Load sensor instances from validated configuration.

        Sensor identifiers are derived as ``{name}@{index}`` and are assumed to
        remain stable for the life of the process. The emitted message format is
        inherited from each sensor, so downstream gossip or LWW merge logic can
        treat all configured sensors uniformly regardless of concrete type.

        Args:
            sensor_configs (tuple[SensorConfig, ...]): Validated sensor definitions
                in declaration order.

        Returns:
            None (None): This method populates ``sensors`` in declaration order.

        Raises:
            RuntimeError: Raised when sensors have already been loaded.
        """
        if self.sensors:
            raise RuntimeError("Sensors already loaded")

        for sensor_config in sensor_configs:
            self.sensors.append(self._build_sensor(sensor_config))

    def _build_sensor(self, sensor_config: SensorConfig) -> SensorInstance:
        """Build one concrete sensor instance from typed configuration.

        Args:
            sensor_config (SensorConfig): Typed configuration for one sensor.

        Returns:
            SensorInstance: Instantiated sensor ready for startup.
        """
        sensor_id = sensor_config.sensor_id
        period_ms = sensor_config.period_ms
        unit = sensor_config.unit

        if sensor_config.sensor_type == SensorType.NUMERIC:
            min_value = _require_config_value(sensor_config.min_value, "min_value")
            max_value = _require_config_value(sensor_config.max_value, "max_value")
            return NumericSensor(
                sensor_id,
                min_value,
                max_value,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.BOOLEAN:
            p_true = _require_config_value(sensor_config.p_true, "p_true")
            return BooleanSensor(
                sensor_id,
                p_true,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.CATEGORICAL:
            return CategoricalSensor(
                sensor_id,
                list(sensor_config.values),
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.INCREMENTAL:
            start = _require_config_value(sensor_config.start, "start")
            step_pct = _require_config_value(sensor_config.step_pct, "step_pct")
            return IncrementalSensor(
                sensor_id,
                start,
                step_pct,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.TREND:
            start = _require_config_value(sensor_config.start, "start")
            slope = _require_config_value(sensor_config.slope, "slope")
            noise = _require_config_value(sensor_config.noise, "noise")
            return TrendSensor(
                sensor_id,
                start,
                slope,
                noise,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.SPIKE:
            baseline = _require_config_value(sensor_config.baseline, "baseline")
            spike_height = _require_config_value(
                sensor_config.spike_height,
                "spike_height",
            )
            p_spike = _require_config_value(sensor_config.p_spike, "p_spike")
            return SpikeSensor(
                sensor_id,
                baseline,
                spike_height,
                p_spike,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        if sensor_config.sensor_type == SensorType.WAVE:
            amplitude = _require_config_value(sensor_config.amplitude, "amplitude")
            frequency = _require_config_value(sensor_config.frequency, "frequency")
            return WaveSensor(
                sensor_id,
                amplitude,
                frequency,
                period_ms,
                callback=self.callback,
                unit=unit,
            )

        base = _require_config_value(sensor_config.base, "base")
        noise = _require_config_value(sensor_config.noise, "noise")
        return NoiseSensor(
            sensor_id,
            base,
            noise,
            period_ms,
            callback=self.callback,
            unit=unit,
        )

    def start_all(self) -> None:
        """Start every loaded sensor publisher.

        Args:
            None (None): This method operates on loaded sensors only.

        Returns:
            None (None): This method starts each managed sensor in order.
        """
        for sensor in self.sensors:
            sensor.start()

    def stop_all(self) -> None:
        """Stop every loaded sensor publisher.

        Args:
            None (None): This method operates on loaded sensors only.

        Returns:
            None (None): This method stops each managed sensor in order.
        """
        for sensor in self.sensors:
            sensor.stop()


def _require_config_value(value: float | None, field_name: str) -> float:
    """Assert that a required numeric sensor field was populated by config parsing.

    Args:
        value (float | None): Parsed config value.
        field_name (str): SensorConfig field name used in the defensive error.

    Returns:
        float: Non-null numeric config value.

    Raises:
        RuntimeError: If configuration parsing produced an unexpected ``None`` value.
    """
    if value is None:
        raise RuntimeError(f"Missing required sensor config field: {field_name}")
    return value
