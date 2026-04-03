"""Define a sensor that emits continuous values from a numeric interval.

Responsibilities:
    Generate independent numeric observations within configured bounds and
    publish them using the shared message format expected by downstream gossip
    dissemination and LWW state consumers.
"""

import random

from sensors.base_sensor import BaseSensor
from utils.typing import SensorCallback


class NumericSensor(BaseSensor):
    """Represent a sensor that samples uniformly from a closed-open range.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (SensorCallback): Consumer for emitted sensor
            messages.
        unit (str | None): Optional engineering unit included in metadata.
        min_val (float): Lower bound for generated values.
        max_val (float): Upper bound for generated values.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        min_val: int | float,
        max_val: int | float,
        period_ms: int | float,
        callback: SensorCallback,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the numeric range contract.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            min_val (int | float): Lower bound for generated values.
            max_val (int | float): Upper bound for generated values.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (SensorCallback): Consumer invoked for
                each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.

        Raises:
            ValueError: Raised when `min_val` is greater than or equal to
                `max_val`.
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
            callback=callback,
            unit=unit,
        )

        self.min_val = min_val
        self.max_val = max_val

    def generate_value(self) -> float:
        """Sample a numeric reading from the configured interval.

        Returns:
            float (float): Uniformly distributed value between `min_val` and
                `max_val`.
        """
        return random.uniform(self.min_val, self.max_val)
