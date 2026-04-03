"""Define a Bernoulli sensor for binary state emission.

Responsibilities:
    Produce boolean readings with a configured true probability and publish them
    through the shared sensor message contract so downstream replicas can treat
    each emission as an independent observation.
"""

import random
from collections.abc import Callable
from typing import Any

from sensors.base_sensor import BaseSensor


class BooleanSensor(BaseSensor):
    """Represent a binary sensor that samples true and false outcomes.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (Callable[[dict[str, Any]], None]): Consumer for emitted sensor
            messages.
        unit (str | None): Optional engineering unit included in metadata.
        p_true (int | float): Probability threshold for emitting `True` on each
            independent sample.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        p_true: int | float,
        period_ms: int | float,
        callback: Callable[[dict[str, Any]], None],
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the binary sampling parameters.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            p_true (int | float): Probability threshold for a `True` reading.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (Callable[[dict[str, Any]], None]): Consumer invoked for
                each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.
        """
        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            callback=callback,
            unit=unit,
        )
        self.p_true = p_true

    def generate_value(self) -> bool:
        """Sample a boolean reading for the next observation.

        Returns:
            bool (bool): `True` when the sample falls below `p_true`; otherwise
                `False`.
        """
        return random.random() < self.p_true
