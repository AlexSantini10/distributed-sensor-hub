"""Define a sensor that occasionally emits elevated spike values.

Responsibilities:
    Model bursty behavior as a baseline stream with probabilistic spikes while
    keeping each emitted reading compatible with the shared message format used
    across the distributed system.
"""

import random

from sensors.base_sensor import BaseSensor
from utils.typing import SensorCallback


class SpikeSensor(BaseSensor):
    """Represent a sensor with sparse high-amplitude events.

    Attributes:
        sensor_id (str): Stable sensor identifier inherited from the base
            contract.
        period_ms (int | float): Emission period in milliseconds.
        callback (SensorCallback | None): Consumer for
            emitted sensor messages.
        unit (str | None): Optional engineering unit included in metadata.
        baseline (int | float): Value emitted when no spike occurs.
        spike_height (int | float): Additional value added during a spike.
        p_spike (int | float): Probability threshold for spike emission.
        _stop_event (threading.Event): Stop signal inherited from the base
            sensor lifecycle.
        _thread (threading.Thread | None): Background publisher thread
            inherited from the base sensor lifecycle.
    """

    def __init__(
        self,
        sensor_id: str,
        baseline: int | float,
        spike_height: int | float,
        p_spike: int | float,
        period_ms: int | float,
        callback: SensorCallback | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize the baseline and spike parameters.

        Args:
            sensor_id (str): Stable identifier attached to emitted messages.
            baseline (int | float): Value emitted when no spike occurs.
            spike_height (int | float): Additional value added during a spike.
            p_spike (int | float): Probability threshold for spike emission.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (SensorCallback | None): Consumer invoked
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
