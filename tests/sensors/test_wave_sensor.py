import pytest
from sensors.wave_sensor import WaveSensor


@pytest.mark.sensors
def test_wave_sensor_output_within_amplitude():
    s = WaveSensor("wave", amplitude=5, frequency=1, period_ms=100, callback=None)

    v = s.generate_value()

    assert -5 <= v <= 5
