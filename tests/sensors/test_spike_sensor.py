"""Validate spike sensor output modes.

Responsibilities:
    - Assert that generated samples are either the baseline or the configured spike value.
"""

import pytest

from sensors.spike_sensor import SpikeSensor


@pytest.mark.sensors
def test_spike_sensor_baseline_or_spike() -> None:
    """Assert that spike samples stay within the two configured output levels.

    Returns:
        None: This test asserts the baseline-versus-spike contract.
    """
    s = SpikeSensor("spike", baseline=10, spike_height=50, p_spike=0.5, period_ms=100, callback=None)

    value = s.generate_value()

    assert value == 10 or value == 60
