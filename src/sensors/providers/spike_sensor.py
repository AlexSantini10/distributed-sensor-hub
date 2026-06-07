"""Define a sensor that occasionally emits elevated spike values."""

import random

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class SpikeSensor(BaseSensor):
    """Represent a sensor with sparse high-amplitude events.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        handler (SensorHandler | None): Ingestion boundary for emitted
            readings.
        unit (str | None): Optional engineering unit included in metadata.
        baseline (int | float): Value emitted when no spike occurs.
        spike_height (int | float): Additional value added during a spike.
        p_spike (int | float): Probability threshold for spike emission.
    """

    def __init__(
        self,
        sensor_id: str,
        baseline: int | float,
        spike_height: int | float,
        p_spike: int | float,
        period_ms: int | float,
        handler: SensorHandler | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize the baseline and spike parameters.

        Args:
            sensor_id (str): Stable identifier attached to emitted readings.
            baseline (int | float): Value emitted when no spike occurs.
            spike_height (int | float): Additional value added during a spike.
            p_spike (int | float): Probability threshold for spike emission.
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
        self.baseline = baseline
        self.spike_height = spike_height
        self.p_spike = p_spike

    def generate_value(self) -> int | float:
        """Sample either the baseline or a spiked reading.

        Returns:
            int | float (int | float): Baseline value or baseline plus spike
                height for the next observation.
        """
        if random.random() < self.p_spike:
            return self.baseline + self.spike_height
        return self.baseline
