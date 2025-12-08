import pytest
import time
from sensors.base_sensor import BaseSensor


@pytest.mark.sensors
def test_base_sensor_generate_not_implemented():
    s = BaseSensor("base", 100)
    with pytest.raises(NotImplementedError):
        s.generate_value()


@pytest.mark.sensors
def test_base_sensor_start_stop():
    results = []

    class Dummy(BaseSensor):
        def generate_value(self):
            return 1

    s = Dummy("dummy", 50, lambda sid, val, ts: results.append((sid, val, ts)))

    s.start()
    time.sleep(0.15)
    s.stop()

    assert len(results) >= 1
