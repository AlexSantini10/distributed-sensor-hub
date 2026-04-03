"""Define a sensor that emits continuous values from a numeric interval."""

import random

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class NumericSensor(BaseSensor):
    """Represent a sensor that samples uniformly from a closed-open range.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        min_val (float): Lower bound for generated values.
        max_val (float): Upper bound for generated values.
    """

    def __init__(
        self,
        sensor_id: str,
        min_val: int | float,
        max_val: int | float,
        period_ms: int | float,
        handler: SensorHandler | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the numeric range contract.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            min_val (int | float): Lower bound for generated values.
            max_val (int | float): Upper bound for generated values.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.

        Raises:
            ValueError: Raised when ``min_val`` is greater than or equal to
                ``max_val``.
        """
        min_val = float(min_val)
        max_val = float(max_val)

        if min_val >= max_val:
            raise ValueError(
                f"min_val must be < max_val (got {min_val} >= {max_val})"
            )

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            handler=handler,
            unit=unit,
        )

        self.min_val = min_val
        self.max_val = max_val

    def generate_value(self) -> float:
        """Sample a numeric reading from the configured interval.

        Returns:
            float (float): Uniformly distributed value between ``min_val`` and
                ``max_val``.
        """
        return random.uniform(self.min_val, self.max_val)
