import pytest
from sensors.trend_sensor import TrendSensor


@pytest.mark.sensors
def test_trend_sensor_increasing():
    s = TrendSensor("trend", start=0, slope=1, noise=0, period_ms=100, callback=None)

    v1 = s.generate_value()
    v2 = s.generate_value()
    v3 = s.generate_value()

    assert v1 < v2 < v3
