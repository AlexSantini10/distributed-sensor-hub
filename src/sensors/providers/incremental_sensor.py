"""Define a sensor that evolves by bounded percentage drift."""

import random

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class IncrementalSensor(BaseSensor):
    """Represent a stateful sensor with bounded relative movement.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        value (float): Current local state used to derive the next reading.
        step_pct (float): Maximum absolute percentage change applied per
            emission.
    """

    def __init__(
        self,
        sensor_id: str,
        start: int | float,
        step_pct: int | float,
        period_ms: int | float,
        handler: SensorHandler | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the starting value and drift envelope.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            start (int | float): Initial value for the local sensor state.
            step_pct (int | float): Maximum percentage delta applied per
                emission.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.

        Raises:
            ValueError: Raised when ``step_pct`` is negative.
        """
        if step_pct < 0:
            raise ValueError("step_pct must be >= 0")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            handler=handler,
            unit=unit,
        )

        self.value = float(start)
        self.step_pct = float(step_pct)

    def generate_value(self) -> float:
        """Advance the local state and return the next reading.

        Returns:
            float (float): Updated sensor value after applying bounded drift.
        """
        delta = abs(self.value) * (self.step_pct / 100.0)

        if delta > 0:
            self.value += random.uniform(-delta, delta)

        return self.value
