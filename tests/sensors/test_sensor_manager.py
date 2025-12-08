import os
import pytest

from sensors.sensor_manager import SensorManager
from sensors.numeric_sensor import NumericSensor


@pytest.mark.sensors
def test_sensor_manager_load_from_env(monkeypatch):
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
    assert mgr.sensors[0].sensor_id == "temp1"
