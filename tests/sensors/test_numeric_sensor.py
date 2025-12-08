import pytest
from sensors.numeric_sensor import NumericSensor


@pytest.mark.sensors
def test_numeric_sensor_range():
    s = NumericSensor("num", 10, 20, 100, "C", None)
    value = s.generate_value()
    assert 10 <= value <= 20
