"""Define a finite deterministic sensor provider for integration scenarios."""

from __future__ import annotations

import random
import time

from sensors.contracts import SensorHandler
from sensors.providers.base_sensor import BaseSensor


class FiniteTestSensor(BaseSensor):
    """Emit a deterministic finite update sequence and stop automatically."""

    def __init__(
        self,
        sensor_id: str,
        *,
        period_ms: int | float,
        seed: int,
        max_updates: int,
        start_ts_ms: int,
        handler: SensorHandler | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize deterministic finite emission settings."""
        if max_updates <= 0:
            raise ValueError("max_updates must be > 0")
        if start_ts_ms < 0:
            raise ValueError("start_ts_ms must be >= 0")

        super().__init__(
            sensor_id=sensor_id,
            period_ms=period_ms,
            handler=handler,
            unit=unit,
        )
        self.seed = int(seed)
        self.max_updates = int(max_updates)
        self.start_ts_ms = int(start_ts_ms)

    def generate_value(self) -> float:
        """Unused by the custom finite loop implementation."""
        raise RuntimeError("FiniteTestSensor uses a custom emission loop")

    def _loop(self) -> None:
        """Run deterministic bounded emissions with explicit timestamps."""
        rng = random.Random(self.seed)
        emitted = 0
        next_deadline = time.monotonic()
        next_ts_ms = self.start_ts_ms
        period_step_ms = int(self.period_ms)
        if period_step_ms <= 0:
            period_step_ms = 1

        while not self._stop_event.is_set() and emitted < self.max_updates:
            value = round(rng.uniform(0.0, 100.0), 6)
            self._emit_reading(
                self._build_reading(
                    value=value,
                    observed_at_ms=next_ts_ms,
                )
            )
            emitted += 1
            next_ts_ms += period_step_ms

            if emitted >= self.max_updates:
                break

            next_deadline += self.period_ms / 1000.0
            sleep_time = next_deadline - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)
