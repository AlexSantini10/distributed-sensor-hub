"""Validate shared sensor base-class contracts."""

import time

import pytest

from sensors.contracts import SensorReading
from sensors.providers.base_sensor import BaseSensor


@pytest.mark.sensors
def test_base_sensor_generate_not_implemented() -> None:
    """Assert that the base sensor requires subclasses to implement generation.

    Returns:
        None: This test asserts the abstract generation contract.
    """
    s = BaseSensor("base", 100, handler=None)
    with pytest.raises(NotImplementedError):
        s.generate_value()


@pytest.mark.sensors
def test_base_sensor_start_stop() -> None:
    """Assert that the base sensor loop invokes the handler with readings.

    Returns:
        None: This test asserts start-stop callback behavior.
    """
    results = []

    class Dummy(BaseSensor):
        """Provide a deterministic concrete sensor for start-stop testing."""

        def generate_value(self) -> int:
            """Return a constant value for deterministic assertions.

            Returns:
                int: Constant sample value used by the test.
            """
            return 1

    class RecordingHandler:
        """Record emitted readings for assertions."""

        def handle(self, reading: SensorReading) -> None:
            """Record one emitted reading.

            Args:
                reading (SensorReading): Reading emitted by the base sensor loop.

            Returns:
                None: This helper appends event tuples to the capture list.
            """
            results.append(
                (reading.sensor_id, reading.value, reading.observed_at_ms)
            )

    s = Dummy("dummy", 50, RecordingHandler())

    s.start()
    time.sleep(0.15)
    s.stop()

    assert len(results) >= 1
    assert results[0][0] == "dummy"
