import pytest
from sensors.incremental_sensor import IncrementalSensor


@pytest.mark.sensors
def test_incremental_sensor_updates_correctly():
    s = IncrementalSensor("inc", start=100, step_pct=10, period_ms=100, callback=None)

    v1 = s.generate_value()
    v2 = s.generate_value()
    v3 = s.generate_value()

    assert v2 != v1
    assert v3 != v2
    assert v1 > 0
