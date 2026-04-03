"""Validate bounded noise sensor output.

Responsibilities:
    - Assert that generated samples remain within the configured noise envelope.
"""

import pytest

from sensors.providers.noise_sensor import NoiseSensor


@pytest.mark.sensors
def test_noise_sensor_range() -> None:
    """Assert that noisy samples stay within ``base +/- noise`` bounds.

    Returns:
        None: This test asserts the configured output envelope.
    """
    s = NoiseSensor("noise", base=10, noise=3, period_ms=100, handler=None)
    v = s.generate_value()

    assert 7 <= v <= 13
