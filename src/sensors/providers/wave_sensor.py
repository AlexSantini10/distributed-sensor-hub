"""Define a sensor that emits a sinusoidal waveform over wall-clock time."""

import math
import time

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class WaveSensor(BaseSensor):
    """Represent a sensor whose output follows a sine wave.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        amplitude (int | float): Peak magnitude of the waveform.
        frequency (int | float): Wave frequency in cycles per second.
        start_time (float): Reference wall-clock timestamp used to compute phase
            progression.
    """

    def __init__(
        self,
        sensor_id: str,
        amplitude: int | float,
        frequency: int | float,
        period_ms: int | float,
        handler: SensorHandler | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize waveform parameters and phase reference.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            amplitude (int | float): Peak magnitude of the waveform.
            frequency (int | float): Wave frequency in cycles per second.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked for each
                emitted reading.
            unit (str | None): Optional engineering unit stored in metadata.

        Returns:
            None: This constructor initializes the provider instance.
        """
        super().__init__(
            sensor_id,
            period_ms,
            handler,
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
