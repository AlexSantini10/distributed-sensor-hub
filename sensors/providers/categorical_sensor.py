"""Define a sensor that emits values from a fixed category set."""

import random
from collections.abc import Sequence

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class CategoricalSensor(BaseSensor):
    """Represent a sensor that samples from a finite category list.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        categories (list[str]): Allowed output domain for emitted readings.
    """

    def __init__(
        self,
        sensor_id: str,
        categories: Sequence[str],
        period_ms: int | float,
        handler: SensorHandler | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the categorical output domain.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            categories (Sequence[str]): Non-empty set of categories eligible for
                emission.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.

        Raises:
            ValueError: Raised when ``categories`` is empty.
        """
        if not categories:
            raise ValueError("CategoricalSensor requires at least one category")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            handler=handler,
            unit=unit,
        )
        self.categories = list(categories)

    def generate_value(self) -> str:
        """Select a category for the next observation.

        Returns:
            str (str): One configured category chosen for the outgoing reading.
        """
        return random.choice(self.categories)
