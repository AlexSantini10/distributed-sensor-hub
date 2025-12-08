import pytest
from sensors.noise_sensor import NoiseSensor


@pytest.mark.sensors
def test_noise_sensor_range():
    s = NoiseSensor("noise", base=10, noise=3, period_ms=100, callback=None)
    v = s.generate_value()

    assert 7 <= v <= 13
