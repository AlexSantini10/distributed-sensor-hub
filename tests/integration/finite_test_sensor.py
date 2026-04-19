"""Provide a finite deterministic sensor provider for integration tests.

Responsibilities:
    - Implement the standard sensor-provider lifecycle used by runtime wiring.
    - Emit deterministic readings at a fixed interval.
    - Stop automatically after a bounded number of updates or duration.
    - Record all emitted readings for later test assertions.
"""

from __future__ import annotations

import random
import threading
import time

from sensors.contracts import SensorHandler, SensorReading


class FiniteTestSensor:
    """Emit deterministic finite sensor updates for integration tests."""

    def __init__(
        self,
        sensor_id: str,
        *,
        interval_seconds: float,
        seed: int = 0,
        max_updates: int | None = None,
        duration_seconds: float | None = None,
        handler: SensorHandler | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize a bounded deterministic provider.

        Args:
            sensor_id (str): Stable sensor identifier for emitted readings.
            interval_seconds (float): Fixed spacing between emissions.
            seed (int): Random seed used for deterministic value generation.
            max_updates (int | None): Maximum number of readings to emit.
            duration_seconds (float | None): Maximum run duration in seconds.
            handler (SensorHandler | None): Optional handler receiving readings.
            unit (str | None): Optional unit included in reading metadata.

        Raises:
            ValueError: If no finite bound is configured or inputs are invalid.
        """
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_updates is None and duration_seconds is None:
            raise ValueError("Either max_updates or duration_seconds must be provided")
        if max_updates is not None and max_updates <= 0:
            raise ValueError("max_updates must be > 0 when provided")
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0 when provided")

        self.sensor_id = sensor_id
        self.interval_seconds = float(interval_seconds)
        self.seed = seed
        self.max_updates = max_updates
        self.duration_seconds = duration_seconds
        self.handler = handler
        self.unit = unit

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()
        self._emitted_readings: list[SensorReading] = []

    def set_handler(self, handler: SensorHandler | None) -> None:
        """Attach or clear the ingestion handler used for future readings."""
        with self._lifecycle_lock:
            self.handler = handler

    @property
    def emitted_readings(self) -> tuple[SensorReading, ...]:
        """Return a copy of all emitted readings for assertions."""
        with self._lifecycle_lock:
            return tuple(self._emitted_readings)

    def is_running(self) -> bool:
        """Report whether the provider thread is currently alive."""
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    def _should_stop(self, *, started_at: float, emitted_count: int) -> bool:
        """Check finite stop conditions."""
        if self.max_updates is not None and emitted_count >= self.max_updates:
            return True
        if self.duration_seconds is not None:
            elapsed = time.monotonic() - started_at
            if elapsed >= self.duration_seconds:
                return True
        return False

    def _build_reading(self, value: float, observed_at_ms: int) -> SensorReading:
        """Create one normalized reading."""
        return SensorReading(
            sensor_id=self.sensor_id,
            value=value,
            observed_at_ms=observed_at_ms,
            meta={
                "unit": self.unit,
                "period_ms": int(self.interval_seconds * 1000),
            },
        )

    def _emit(self, reading: SensorReading) -> None:
        """Store and forward one reading."""
        handler = self.handler
        if handler is None:
            raise TypeError("Sensor provider has no configured handler")
        with self._lifecycle_lock:
            self._emitted_readings.append(reading)
        handler.handle(reading)

    def _loop(self) -> None:
        """Run deterministic finite emissions."""
        rng = random.Random(self.seed)
        started_at = time.monotonic()
        emitted_count = 0
        next_deadline = started_at

        while not self._stop_event.is_set():
            if self._should_stop(started_at=started_at, emitted_count=emitted_count):
                break

            value = round(rng.uniform(0.0, 100.0), 6)
            observed_at_ms = int(time.time() * 1000)
            self._emit(self._build_reading(value=value, observed_at_ms=observed_at_ms))
            emitted_count += 1

            if self._should_stop(started_at=started_at, emitted_count=emitted_count):
                break

            next_deadline += self.interval_seconds
            sleep_seconds = next_deadline - time.monotonic()
            if sleep_seconds > 0:
                self._stop_event.wait(timeout=sleep_seconds)

    def start(self) -> None:
        """Start deterministic emissions in a background thread."""
        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name=f"finite-test-sensor-{self.sensor_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop emissions and wait briefly for thread termination."""
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread

        if thread is None:
            return
        if thread is threading.current_thread():
            return
        if thread.ident is None:
            return

        thread.join(timeout=2.0)
