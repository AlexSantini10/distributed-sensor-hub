import pytest
import time
from sensors.base_sensor import BaseSensor


@pytest.mark.sensors
def test_base_sensor_generate_not_implemented():
	s = BaseSensor("base", 100, callback=lambda *_: None)
	with pytest.raises(NotImplementedError):
		s.generate_value()


@pytest.mark.sensors
def test_base_sensor_start_stop():
	results = []

	class Dummy(BaseSensor):
		def generate_value(self):
			return 1

	def cb(evt):
		results.append((evt["sensor_id"], evt["value"], evt["ts_ms"]))

	s = Dummy("dummy", 50, cb)

	s.start()
	time.sleep(0.15)
	s.stop()

	assert len(results) >= 1
	assert results[0][0] == "dummy"
