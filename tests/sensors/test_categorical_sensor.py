"""Validate categorical sensor value selection.

Responsibilities:
    - Assert that generated values are always chosen from the configured category set.
"""

import pytest

from sensors.providers.categorical_sensor import CategoricalSensor


@pytest.mark.sensors
def test_categorical_sensor_values() -> None:
    """Assert that generated categorical values come from the configured choices.

    Returns:
        None: This test asserts category membership.
    """
    choices = ["red", "green", "blue"]
    s = CategoricalSensor("cat", choices, 100, None)
    value = s.generate_value()

    assert value in choices
