"""Validate numeric sensor bounds.

Responsibilities:
    - Assert that generated numeric values stay within configured limits.
"""

import pytest

from sensors.providers.numeric_sensor import NumericSensor


@pytest.mark.sensors
def test_numeric_sensor_range() -> None:
    """Assert that numeric samples stay within the configured range.

    Returns:
        None: This test asserts numeric output bounds.
    """
    s = NumericSensor("num", 10, 20, 100, handler=None, unit="C")
    value = s.generate_value()
    assert 10 <= value <= 20
