"""Define provider registration and lifecycle orchestration for sensor inputs.

Extension point for sensor integrations.

Responsibilities:
    Translate validated sensor configuration into sensor providers, bind each
    provider to the shared ingestion handler, and coordinate provider lifecycle
    without coupling providers to replicated state or networking logic.
"""

from __future__ import annotations

from collections.abc import Callable

from sensors.contracts import SensorHandler, SensorProvider
from sensors.providers.boolean_sensor import BooleanSensor
from sensors.providers.categorical_sensor import CategoricalSensor
from sensors.providers.incremental_sensor import IncrementalSensor
from sensors.providers.noise_sensor import NoiseSensor
from sensors.providers.numeric_sensor import NumericSensor
from sensors.providers.spike_sensor import SpikeSensor
from sensors.providers.trend_sensor import TrendSensor
from sensors.providers.wave_sensor import WaveSensor
from utils.config import SensorConfig, SensorType


type SensorProviderFactory = Callable[[SensorConfig], SensorProvider]


class SensorManager:
    """Represent configuration-driven ownership of sensor providers.

    Extension point for sensor integrations.

    New integrations may either:
        - implement ``SensorProvider`` and register an instance directly, or
        - extend the config-driven factory mapping used for built-in simulated
          providers.

    Attributes:
        handler (SensorHandler): Shared ingestion boundary bound to every managed
            provider.
        sensors (list[SensorProvider]): Managed providers that belong to this
            runtime.
        _factories (dict[SensorType, SensorProviderFactory]): Factory registry
            for config-driven providers.
    """

    def __init__(self, handler: SensorHandler) -> None:
        """Initialize the manager with a shared ingestion boundary.

        Args:
            handler (SensorHandler): Ingestion boundary used by all managed
                providers.

        Returns:
            None: This constructor initializes the manager instance.
        """
        self.handler = handler
        self.sensors: list[SensorProvider] = []
        self._factories: dict[SensorType, SensorProviderFactory] = {
            SensorType.NUMERIC: self._build_numeric_sensor,
            SensorType.BOOLEAN: self._build_boolean_sensor,
            SensorType.CATEGORICAL: self._build_categorical_sensor,
            SensorType.INCREMENTAL: self._build_incremental_sensor,
            SensorType.TREND: self._build_trend_sensor,
            SensorType.SPIKE: self._build_spike_sensor,
            SensorType.WAVE: self._build_wave_sensor,
            SensorType.NOISE: self._build_noise_sensor,
        }

    def load(self, sensor_configs: tuple[SensorConfig, ...]) -> None:
        """Load provider instances from validated configuration.

        Sensor identifiers are derived as ``{name}@{index}`` and are assumed to
        remain stable for the life of the process.

        Args:
            sensor_configs (tuple[SensorConfig, ...]): Validated sensor
                definitions in declaration order.

        Returns:
            None: This method populates ``sensors`` in declaration order.

        Raises:
            RuntimeError: Raised when providers have already been loaded.
        """
        if self.sensors:
            raise RuntimeError("Sensors already loaded")

        for sensor_config in sensor_configs:
            self.register(self._build_sensor(sensor_config))

    def register(self, provider: SensorProvider) -> None:
        """Register one provider instance with the shared ingestion handler.

        Args:
            provider (SensorProvider): Provider instance to manage.

        Returns:
            None: This method binds the shared handler and stores the provider.
        """
        provider.set_handler(self.handler)
        self.sensors.append(provider)

    def _build_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build one provider instance from typed configuration.

        Args:
            sensor_config (SensorConfig): Typed configuration for one sensor.

        Returns:
            SensorProvider: Instantiated provider ready for startup.
        """
        factory = self._factories[sensor_config.sensor_type]
        return factory(sensor_config)

    def _build_numeric_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a numeric simulated provider from config.

        Args:
            sensor_config (SensorConfig): Numeric sensor configuration.

        Returns:
            SensorProvider: Configured numeric provider.
        """
        min_value = _require_config_value(sensor_config.min_value, "min_value")
        max_value = _require_config_value(sensor_config.max_value, "max_value")
        return NumericSensor(
            sensor_config.sensor_id,
            min_value,
            max_value,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_boolean_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a boolean simulated provider from config.

        Args:
            sensor_config (SensorConfig): Boolean sensor configuration.

        Returns:
            SensorProvider: Configured boolean provider.
        """
        p_true = _require_config_value(sensor_config.p_true, "p_true")
        return BooleanSensor(
            sensor_config.sensor_id,
            p_true,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_categorical_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a categorical simulated provider from config.

        Args:
            sensor_config (SensorConfig): Categorical sensor configuration.

        Returns:
            SensorProvider: Configured categorical provider.
        """
        return CategoricalSensor(
            sensor_config.sensor_id,
            list(sensor_config.values),
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_incremental_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build an incremental simulated provider from config.

        Args:
            sensor_config (SensorConfig): Incremental sensor configuration.

        Returns:
            SensorProvider: Configured incremental provider.
        """
        start = _require_config_value(sensor_config.start, "start")
        step_pct = _require_config_value(sensor_config.step_pct, "step_pct")
        return IncrementalSensor(
            sensor_config.sensor_id,
            start,
            step_pct,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_trend_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a trend simulated provider from config.

        Args:
            sensor_config (SensorConfig): Trend sensor configuration.

        Returns:
            SensorProvider: Configured trend provider.
        """
        start = _require_config_value(sensor_config.start, "start")
        slope = _require_config_value(sensor_config.slope, "slope")
        noise = _require_config_value(sensor_config.noise, "noise")
        return TrendSensor(
            sensor_config.sensor_id,
            start,
            slope,
            noise,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_spike_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a spike simulated provider from config.

        Args:
            sensor_config (SensorConfig): Spike sensor configuration.

        Returns:
            SensorProvider: Configured spike provider.
        """
        baseline = _require_config_value(sensor_config.baseline, "baseline")
        spike_height = _require_config_value(
            sensor_config.spike_height,
            "spike_height",
        )
        p_spike = _require_config_value(sensor_config.p_spike, "p_spike")
        return SpikeSensor(
            sensor_config.sensor_id,
            baseline,
            spike_height,
            p_spike,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_wave_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a wave simulated provider from config.

        Args:
            sensor_config (SensorConfig): Wave sensor configuration.

        Returns:
            SensorProvider: Configured wave provider.
        """
        amplitude = _require_config_value(sensor_config.amplitude, "amplitude")
        frequency = _require_config_value(sensor_config.frequency, "frequency")
        return WaveSensor(
            sensor_config.sensor_id,
            amplitude,
            frequency,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def _build_noise_sensor(self, sensor_config: SensorConfig) -> SensorProvider:
        """Build a noise simulated provider from config.

        Args:
            sensor_config (SensorConfig): Noise sensor configuration.

        Returns:
            SensorProvider: Configured noise provider.
        """
        base = _require_config_value(sensor_config.base, "base")
        noise = _require_config_value(sensor_config.noise, "noise")
        return NoiseSensor(
            sensor_config.sensor_id,
            base,
            noise,
            sensor_config.period_ms,
            handler=None,
            unit=sensor_config.unit,
        )

    def start_all(self) -> None:
        """Start every loaded sensor provider.

        Returns:
            None: This method starts each managed provider in order.
        """
        for sensor in self.sensors:
            sensor.start()

    def stop_all(self) -> None:
        """Stop every loaded sensor provider.

        Returns:
            None: This method stops each managed provider in order.
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
        RuntimeError: If configuration parsing produced an unexpected ``None``
            value.
    """
    if value is None:
        raise RuntimeError(f"Missing required sensor config field: {field_name}")
    return value
