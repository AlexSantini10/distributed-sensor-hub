import pytest
from sensors.categorical_sensor import CategoricalSensor


@pytest.mark.sensors
def test_categorical_sensor_values():
    choices = ["red", "green", "blue"]
    s = CategoricalSensor("cat", choices, 100, None)
    value = s.generate_value()

    assert value in choices
