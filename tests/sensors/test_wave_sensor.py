"""Validate wave sensor amplitude constraints.

Responsibilities:
    - Assert that generated wave samples stay within the configured amplitude.
"""

import pytest

from sensors.wave_sensor import WaveSensor


@pytest.mark.sensors
def test_wave_sensor_output_within_amplitude() -> None:
    """Assert that wave samples remain bounded by amplitude.

    Returns:
        None: This test asserts the configured oscillation envelope.
    """
    s = WaveSensor("wave", amplitude=5, frequency=1, period_ms=100, callback=None)

    v = s.generate_value()

    assert -5 <= v <= 5
