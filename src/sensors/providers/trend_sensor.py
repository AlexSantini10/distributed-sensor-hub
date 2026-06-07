"""Define a sensor that evolves with deterministic trend and bounded noise."""

import random

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class TrendSensor(BaseSensor):
    """Represent a sensor with persistent trend state across emissions.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        value (int | float): Current local state advanced on each emission.
        slope (int | float): Deterministic increment applied per emission.
        noise (int | float): Maximum absolute noise added after the slope.
    """

    def __init__(
        self,
        sensor_id: str,
        start: int | float,
        slope: int | float,
        noise: int | float,
        period_ms: int | float,
        handler: SensorHandler | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize the starting value, slope, and noise envelope.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            start (int | float): Initial value for the local sensor state.
            slope (int | float): Deterministic increment applied per emission.
            noise (int | float): Maximum absolute noise added per emission.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.
        """
        super().__init__(
            sensor_id,
            period_ms,
            handler,
            unit=unit,
        )
        self.value = start
        self.slope = slope
        self.noise = noise

    def generate_value(self) -> int | float:
        """Advance the trend state and return the next reading.

        Returns:
            int | float (int | float): Updated sensor value after applying the
                configured slope and bounded noise.
        """
        self.value += self.slope
        self.value += random.uniform(-self.noise, self.noise)
        return self.value
