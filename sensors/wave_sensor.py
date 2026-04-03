"""Define a sensor that emits a sinusoidal waveform over wall-clock time.

Responsibilities:
    Produce deterministic periodic readings from amplitude and frequency
    parameters, and publish them through the common message format used by the
    distributed event pipeline.
"""

import math
import time
from collections.abc import Callable
from typing import Any

from sensors.base_sensor import BaseSensor


class WaveSensor(BaseSensor):
    """Represent a sensor whose output follows a sine wave.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (Callable[[dict[str, Any]], None] | None): Consumer for
            emitted sensor messages.
        unit (str | None): Optional engineering unit included in metadata.
        amplitude (int | float): Peak magnitude of the waveform.
        frequency (int | float): Wave frequency in cycles per second.
        start_time (float): Reference wall-clock timestamp used to compute phase
            progression.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        amplitude: int | float,
        frequency: int | float,
        period_ms: int | float,
        callback: Callable[[dict[str, Any]], None] | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize waveform parameters and phase reference.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            amplitude (int | float): Peak magnitude of the waveform.
            frequency (int | float): Wave frequency in cycles per second.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (Callable[[dict[str, Any]], None] | None): Consumer invoked
                for each emitted message.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.
        """
        super().__init__(
            sensor_id,
            period_ms,
            callback,
            unit=unit,
        )
        self.amplitude = amplitude
        self.frequency = frequency
        self.start_time = time.time()

    def generate_value(self) -> float:
        """Compute the waveform value for the current phase.

        Returns:
            float (float): Sine-wave value derived from elapsed wall-clock time.
        """
        t = time.time() - self.start_time
        return self.amplitude * math.sin(2 * math.pi * self.frequency * t)
