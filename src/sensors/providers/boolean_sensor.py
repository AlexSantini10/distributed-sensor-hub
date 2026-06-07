"""Define a Bernoulli sensor for binary state emission."""

import random

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class BooleanSensor(BaseSensor):
    """Represent a binary sensor that samples true and false outcomes.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        p_true (int | float): Probability threshold for emitting ``True`` on
            each independent sample.
    """

    def __init__(
        self,
        sensor_id: str,
        p_true: int | float,
        period_ms: int | float,
        handler: SensorHandler | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the binary sampling parameters.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            p_true (int | float): Probability threshold for a ``True`` reading.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.
        """
        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            handler=handler,
            unit=unit,
        )
        self.p_true = p_true

    def generate_value(self) -> bool:
        """Sample a boolean reading for the next observation.

        Returns:
            bool (bool): ``True`` when the sample falls below ``p_true``;
                otherwise ``False``.
        """
        return random.random() < self.p_true
