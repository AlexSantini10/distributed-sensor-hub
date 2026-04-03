"""Validate shared sensor base-class contracts.

Responsibilities:
    - Assert that abstract value generation is enforced.
    - Verify that the sensor loop emits timestamped events through the callback.
"""

import time

import pytest

from sensors.base_sensor import BaseSensor
from utils.typing import SensorCallback


@pytest.mark.sensors
def test_base_sensor_generate_not_implemented() -> None:
    """Assert that the base sensor requires subclasses to implement generation.

    Returns:
        None: This test asserts the abstract generation contract.
    """
    s = BaseSensor("base", 100, callback=lambda *_: None)
    with pytest.raises(NotImplementedError):
        s.generate_value()


@pytest.mark.sensors
def test_base_sensor_start_stop() -> None:
    """Assert that the base sensor loop invokes the callback with event payloads.

    Returns:
        None: This test asserts start-stop callback behavior.
    """
    results = []

    class Dummy(BaseSensor):
        """Provide a deterministic concrete sensor for start-stop testing.

        Attributes:
            sensor_id (str): Inherited logical sensor identifier.
            period_ms (int): Inherited sample cadence.
            callback (SensorCallback | None): Inherited event sink called by the sensor loop.
        """

        def generate_value(self) -> int:
            """Return a constant value for deterministic assertions.

            Returns:
                int: Constant sample value used by the test.
            """
            return 1

    def cb(evt: dict[str, object]) -> None:
        """Record emitted sensor events for assertions.

        Args:
            evt (dict): Event payload emitted by the base sensor loop.

        Returns:
            None: This helper appends event tuples to the capture list.
        """
        results.append((evt["sensor_id"], evt["value"], evt["ts_ms"]))

    s = Dummy("dummy", 50, cb)

    s.start()
    time.sleep(0.15)
    s.stop()

    assert len(results) >= 1
    assert results[0][0] == "dummy"
