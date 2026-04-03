"""Define the base implementation for simulated push-based sensor providers.

Extension point for sensor integrations.

Responsibilities:
    Model a local sensor as a single-writer provider that emits
    ``SensorReading`` values through a ``SensorHandler``, preserve a stable
    lifecycle contract for simulated sensors, and keep data production fully
    decoupled from state, networking, and gossip concerns.
"""

from __future__ import annotations

import threading
import time

from sensors.contracts import SensorHandler, SensorReading
from utils.typing import JsonValue, SensorMetaDict


class BaseSensor:
    """Represent a periodic simulated provider that emits structured readings.

    Extension point for sensor integrations.

    Attributes:
        sensor_id (str): Stable sensor identifier included in every emitted
            reading and assumed unique within the deployment.
        period_ms (int | float): Emission period in milliseconds for successive
            readings.
        handler (SensorHandler | None): Ingestion boundary that receives
            provider readings.
        unit (str | None): Optional engineering unit propagated in reading
            metadata.
        _stop_event (threading.Event): Coordination primitive that signals loop
            termination.
        _thread (threading.Thread | None): Background worker responsible for
            periodic emission while the provider is running.
        _lifecycle_lock (threading.Lock): Mutex protecting start/stop and
            handler updates.
    """

    def __init__(
        self,
        sensor_id: str,
        period_ms: int | float,
        handler: SensorHandler | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the provider contract and lifecycle state.

        Args:
            sensor_id (str): Stable identifier attached to all generated
                readings.
            period_ms (int | float): Emission cadence in milliseconds.
            handler (SensorHandler | None): Ingestion boundary invoked once per
                generated reading.
            unit (str | None): Optional engineering unit stored in reading
                metadata.

        Returns:
            None: This constructor initializes the provider instance.
        """
        self.sensor_id = sensor_id
        self.period_ms = period_ms
        self.handler = handler
        self.unit = unit

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    def set_handler(self, handler: SensorHandler | None) -> None:
        """Attach or clear the ingestion handler used for future readings.

        Args:
            handler (SensorHandler | None): Handler that will receive future
                readings, or ``None`` to clear the current handler.

        Returns:
            None: This method updates the ingestion target in place.
        """
        with self._lifecycle_lock:
            self.handler = handler

    def generate_value(self) -> JsonValue:
        """Produce the next sensor value for publication.

        Returns:
            JsonValue (JsonValue): Sensor-specific value for the outgoing reading.

        Raises:
            NotImplementedError: Raised when a subclass does not provide a value
                generation contract.
        """
        raise NotImplementedError

    def _build_reading(self, value: JsonValue, observed_at_ms: int) -> SensorReading:
        """Build one normalized reading from a generated value.

        Args:
            value (JsonValue): Generated sensor value.
            observed_at_ms (int): Observation timestamp in Unix milliseconds.

        Returns:
            SensorReading (SensorReading): Reading ready for ingestion.
        """
        meta: SensorMetaDict = {
            "unit": self.unit,
            "period_ms": self.period_ms,
        }
        return SensorReading(
            sensor_id=self.sensor_id,
            value=value,
            observed_at_ms=observed_at_ms,
            meta=meta,
        )

    def _emit_reading(self, reading: SensorReading) -> None:
        """Deliver one reading to the configured ingestion handler.

        Args:
            reading (SensorReading): Reading to ingest.

        Returns:
            None: This method delegates to the configured handler.

        Raises:
            TypeError: Raised when the provider has no configured handler.
        """
        handler = self.handler
        if handler is None:
            raise TypeError("Sensor provider has no configured handler")
        handler.handle(reading)

    def _loop(self) -> None:
        """Emit readings at the configured period until the provider stops.

        Data flow is push-based: each generated value is wrapped in a
        ``SensorReading`` and immediately sent to the configured
        ``SensorHandler`` from the provider-owned background thread. The
        observation timestamp is captured before ingestion and must be preserved
        by downstream code.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method runs until the stop signal is observed.
        """
        next_deadline = time.monotonic()
        period_s = self.period_ms / 1000.0

        while not self._stop_event.is_set():
            value = self.generate_value()
            observed_at_ms = int(time.time() * 1000)
            self._emit_reading(self._build_reading(value, observed_at_ms))

            next_deadline += period_s
            sleep_time = next_deadline - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)

    def start(self) -> None:
        """Start publishing readings in a background thread.

        The provider emits readings from its own daemon thread. Startup is
        idempotent.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method either starts the provider thread or leaves
                an already started provider unchanged.
        """
        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name=f"sensor-{self.sensor_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop publishing readings and wait briefly for termination.

        Shutdown is best-effort and safe to call multiple times.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method signals termination and joins the worker
                thread when present.
        """
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread

        if thread is None:
            return
        if thread is threading.current_thread():
            return
        if thread.ident is None:
            return

        thread.join(timeout=2)
