import pytest
from sensors.spike_sensor import SpikeSensor


@pytest.mark.sensors
def test_spike_sensor_baseline_or_spike():
    s = SpikeSensor("spike", baseline=10, spike_height=50, p_spike=0.5, period_ms=100, callback=None)

    value = s.generate_value()

    assert value == 10 or value == 60
