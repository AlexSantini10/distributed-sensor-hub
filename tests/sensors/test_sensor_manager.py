"""Validate sensor-manager environment loading.

Responsibilities:
    - Assert that environment-defined sensors are instantiated with expected types and ids.
"""

from typing import Any

import pytest

from sensors.numeric_sensor import NumericSensor
from sensors.sensor_manager import SensorManager


@pytest.mark.sensors
def test_sensor_manager_load_from_env(monkeypatch: Any) -> None:
    """Assert that environment variables produce the expected sensor instance.

    Args:
        monkeypatch (Any): Pytest monkeypatch fixture used to set environment variables.

    Returns:
        None: This test asserts environment-driven sensor loading.
    """
    monkeypatch.setenv("SENSORS", "1")
    monkeypatch.setenv("SENSOR_0_TYPE", "numeric")
    monkeypatch.setenv("SENSOR_0_NAME", "temp1")
    monkeypatch.setenv("SENSOR_0_MIN", "0")
    monkeypatch.setenv("SENSOR_0_MAX", "100")
    monkeypatch.setenv("SENSOR_0_PERIOD_MS", "500")

    mgr = SensorManager(callback=lambda *_: None)
    mgr.load_from_env()

    assert len(mgr.sensors) == 1
    assert isinstance(mgr.sensors[0], NumericSensor)
    assert mgr.sensors[0].sensor_id == "temp1@0"
