import pytest
from sensors.boolean_sensor import BooleanSensor


@pytest.mark.sensors
def test_boolean_sensor_distribution():
    s = BooleanSensor("bool", p_true=0.8, period_ms=100, callback=None)

    values = [s.generate_value() for _ in range(200)]
    ratio = sum(values) / len(values)

    assert 0.6 <= ratio <= 1.0
