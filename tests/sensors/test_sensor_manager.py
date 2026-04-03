"""Validate sensor-manager environment loading.

Responsibilities:
    - Assert that environment-defined sensors are instantiated with expected types and ids.
"""

import pytest
from pytest import MonkeyPatch

from sensors.numeric_sensor import NumericSensor
from sensors.sensor_manager import SensorManager
from utils.config import load_config


@pytest.mark.sensors
def test_sensor_manager_load_from_env(monkeypatch: MonkeyPatch) -> None:
    """Assert that environment variables produce the expected sensor instance.

    Args:
        monkeypatch (MonkeyPatch): Pytest monkeypatch fixture used to set environment variables.

    Returns:
        None: This test asserts environment-driven sensor loading.
    """
    monkeypatch.setenv("SENSORS", "1")
    monkeypatch.setenv("SENSOR_0_TYPE", "numeric")
    monkeypatch.setenv("SENSOR_0_NAME", "temp1")
    monkeypatch.setenv("SENSOR_0_MIN", "0")
    monkeypatch.setenv("SENSOR_0_MAX", "100")
    monkeypatch.setenv("SENSOR_0_PERIOD_MS", "500")
    monkeypatch.setenv("NODE_ID", "node-1")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "logs/test.log")

    mgr = SensorManager(callback=lambda *_: None)
    mgr.load(load_config().sensors)

    assert len(mgr.sensors) == 1
    assert isinstance(mgr.sensors[0], NumericSensor)
    assert mgr.sensors[0].sensor_id == "temp1@0"
