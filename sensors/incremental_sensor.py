"""Define a sensor that evolves by bounded percentage drift.

Responsibilities:
    Maintain mutable local state across emissions, generate successive readings
    by perturbing the current value within a percentage envelope, and preserve
    a single-writer sequence suitable for downstream LWW consumers.
"""

import random
from collections.abc import Callable
from typing import Any

from sensors.base_sensor import BaseSensor


class IncrementalSensor(BaseSensor):
    """Represent a stateful sensor with bounded relative movement.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (Callable[[dict[str, Any]], None]): Consumer for emitted sensor
            messages.
        unit (str | None): Optional engineering unit included in metadata.
        value (float): Current local state used to derive the next reading.
        step_pct (float): Maximum absolute percentage change applied per
            emission.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        start: int | float,
        step_pct: int | float,
        period_ms: int | float,
        callback: Callable[[dict[str, Any]], None],
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the starting value and drift envelope.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            start (int | float): Initial value for the local sensor state.
            step_pct (int | float): Maximum percentage delta applied per
                emission.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (Callable[[dict[str, Any]], None]): Consumer invoked for
                each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.

        Raises:
            ValueError: Raised when `step_pct` is negative.
        """
        if step_pct < 0:
            raise ValueError("step_pct must be >= 0")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            callback=callback,
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
