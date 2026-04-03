"""Define a sensor that emits values from a fixed category set.

Responsibilities:
    Produce discrete symbolic readings from a configured domain and preserve
    that domain as the contract assumed by downstream message consumers and
    distributed replicas.
"""

import random
from collections.abc import Sequence

from sensors.base_sensor import BaseSensor
from utils.typing import SensorCallback


class CategoricalSensor(BaseSensor):
    """Represent a sensor that samples from a finite category list.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (SensorCallback): Consumer for emitted sensor
            messages.
        unit (str | None): Optional engineering unit included in metadata.
        categories (list[str]): Allowed output domain for emitted readings.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        categories: Sequence[str],
        period_ms: int | float,
        callback: SensorCallback,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the categorical output domain.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            categories (Sequence[str]): Non-empty set of categories eligible for
                emission.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (SensorCallback): Consumer invoked for
                each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.

        Raises:
            ValueError: Raised when `categories` is empty.
        """
        if not categories:
            raise ValueError("CategoricalSensor requires at least one category")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            callback=callback,
            unit=unit,
        )
        self.categories = list(categories)

    def generate_value(self) -> str:
        """Select a category for the next observation.

        Returns:
            str (str): One configured category chosen for the outgoing message.
        """
        return random.choice(self.categories)
