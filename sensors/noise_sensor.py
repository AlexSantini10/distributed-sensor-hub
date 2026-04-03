"""Define a sensor that emits bounded noise around a baseline.

Responsibilities:
    Produce independent numeric observations centered on a configured base value
    and keep the output contract stable for transport and reconciliation by
    downstream distributed components.
"""

import random
from collections.abc import Callable
from typing import Any

from sensors.base_sensor import BaseSensor


class NoiseSensor(BaseSensor):
    """Represent a sensor with symmetric bounded noise around a base value.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (Callable[[dict[str, Any]], None]): Consumer for emitted sensor
            messages.
        unit (str | None): Optional engineering unit included in metadata.
        base (float): Center value for emitted samples.
        noise (float): Maximum absolute deviation from `base` per emission.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        base: int | float,
        noise: int | float,
        period_ms: int | float,
        callback: Callable[[dict[str, Any]], None],
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the baseline and noise envelope.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            base (int | float): Center value for generated readings.
            noise (int | float): Maximum absolute deviation from the base value.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (Callable[[dict[str, Any]], None]): Consumer invoked for
                each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.

        Raises:
            ValueError: Raised when `noise` is negative.
        """
        if noise < 0:
            raise ValueError("noise must be >= 0")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            callback=callback,
            unit=unit,
        )

        self.base = float(base)
        self.noise = float(noise)

    def generate_value(self) -> float:
        """Sample a noisy reading around the configured baseline.

        Returns:
            float (float): Baseline value plus uniformly distributed bounded
                noise.
        """
        return self.base + random.uniform(-self.noise, self.noise)
