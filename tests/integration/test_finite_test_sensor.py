"""Validate deterministic finite sensor behavior for integration tests."""

from __future__ import annotations

import time

import pytest

from sensors.contracts import SensorReading
from tests.integration.finite_test_sensor import FiniteTestSensor


class RecordingHandler:
    """Record emitted readings for assertions."""

    def __init__(self) -> None:
        self.readings: list[SensorReading] = []

    def handle(self, reading: SensorReading) -> None:
        """Store one received reading."""
        self.readings.append(reading)


def _wait_until_stopped(sensor: FiniteTestSensor, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not sensor.is_running():
            return
        time.sleep(0.01)
    raise AssertionError("Sensor did not stop before timeout")


@pytest.mark.integration
def test_finite_sensor_stops_after_max_updates() -> None:
    """Assert max_updates produces finite deterministic output and auto-stop."""
    handler = RecordingHandler()
    sensor = FiniteTestSensor(
        "finite@0",
        interval_seconds=0.01,
        seed=7,
        max_updates=4,
        handler=handler,
        unit="test-unit",
    )

    sensor.start()
    _wait_until_stopped(sensor)

    emitted = sensor.emitted_readings
    assert len(emitted) == 4
    assert len(handler.readings) == 4
    assert emitted == tuple(handler.readings)
    assert all(reading.sensor_id == "finite@0" for reading in emitted)
    assert all(reading.meta["unit"] == "test-unit" for reading in emitted)


@pytest.mark.integration
def test_finite_sensor_sequence_is_deterministic_for_same_seed() -> None:
    """Assert two sensors with same seed emit identical value sequences."""
    first_handler = RecordingHandler()
    second_handler = RecordingHandler()

    first = FiniteTestSensor(
        "finite@a",
        interval_seconds=0.005,
        seed=123,
        max_updates=5,
        handler=first_handler,
    )
    second = FiniteTestSensor(
        "finite@b",
        interval_seconds=0.005,
        seed=123,
        max_updates=5,
        handler=second_handler,
    )

    first.start()
    second.start()
    _wait_until_stopped(first)
    _wait_until_stopped(second)

    first_values = [reading.value for reading in first_handler.readings]
    second_values = [reading.value for reading in second_handler.readings]
    assert first_values == second_values


@pytest.mark.integration
def test_finite_sensor_stops_after_duration_without_max_updates() -> None:
    """Assert duration_seconds bounds runtime when max_updates is absent."""
    handler = RecordingHandler()
    sensor = FiniteTestSensor(
        "finite@duration",
        interval_seconds=0.01,
        seed=5,
        duration_seconds=0.05,
        handler=handler,
    )

    sensor.start()
    _wait_until_stopped(sensor)

    assert len(handler.readings) >= 1
    assert len(handler.readings) <= 10


@pytest.mark.integration
def test_finite_sensor_requires_finite_bound() -> None:
    """Assert construction fails when no stop bound is configured."""
    with pytest.raises(ValueError):
        FiniteTestSensor(
            "finite@invalid",
            interval_seconds=0.01,
            seed=1,
            handler=RecordingHandler(),
        )
