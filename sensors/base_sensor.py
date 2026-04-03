"""Define the base contract for periodic sensor publishers.

Responsibilities:
    Model a local sensor as a single-writer source that emits timestamped
    messages to a callback, enforce a stable message format for downstream
    gossip or LWW consumers, and manage the sensor lifecycle without changing
    payload semantics across sensor implementations.
"""

import threading
import time
from collections.abc import Callable
from typing import Any


class BaseSensor:
    """Represent a periodic sensor that publishes structured readings.

    Attributes:
        sensor_id (str): Stable sensor identifier included in every emitted
            message and assumed unique within the deployment.
        period_ms (int | float): Emission period in milliseconds for successive
            readings.
        callback (Callable[[dict[str, Any]], None] | None): Sink that receives
            sensor messages as atomic dictionaries suitable for transport.
        unit (str | None): Optional engineering unit propagated in message
            metadata.
        _stop_event (threading.Event): Coordination primitive that signals loop
            termination.
        _thread (threading.Thread | None): Background worker responsible for
            periodic emission while the sensor is running.
    """

    def __init__(
        self,
        sensor_id: str,
        period_ms: int | float,
        callback: Callable[[dict[str, Any]], None] | None,
        *,
        unit: str | None = None,
    ) -> None:
        """Initialize the sensor contract and lifecycle state.

        Args:
            sensor_id (str): Stable identifier attached to all generated
                messages.
            period_ms (int | float): Emission cadence in milliseconds.
            callback (Callable[[dict[str, Any]], None] | None): Consumer
                invoked once per generated message.
            unit (str | None): Optional engineering unit stored in message
                metadata.

        Returns:
            None (None): This constructor initializes the sensor instance.
        """
        self.sensor_id = sensor_id
        self.period_ms = period_ms
        self.callback = callback
        self.unit = unit

        self._stop_event = threading.Event()
        self._thread = None

    def generate_value(self) -> Any:
        """Produce the next sensor reading for publication.

        Returns:
            Any (Any): Sensor-specific value to encode in the outgoing message.

        Raises:
            NotImplementedError: Raised when a subclass does not provide a value
                generation contract.
        """
        raise NotImplementedError

    def _loop(self) -> None:
        """Emit readings at the configured period until the sensor stops.

        The callback receives a message with `sensor_id`, `value`, `ts_ms`, and
        `meta`. The `ts_ms` field is the observation timestamp that downstream
        distributed components may use for LWW ordering, so the callback is
        assumed to preserve it without rewriting and to be non-`None` before
        publication begins.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method runs until the stop signal is observed.
        """
        next_deadline = time.monotonic()
        period_s = self.period_ms / 1000.0

        while not self._stop_event.is_set():
            value = self.generate_value()
            ts_ms = int(time.time() * 1000)

            self.callback(
                {
                    "sensor_id": self.sensor_id,
                    "value": value,
                    "ts_ms": ts_ms,
                    "meta": {
                        "unit": self.unit,
                        "period_ms": self.period_ms,
                    },
                }
            )

            next_deadline += period_s
            sleep_time = next_deadline - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)

    def start(self) -> None:
        """Start publishing readings in a background thread.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method either starts the publisher thread or
                leaves an already started sensor unchanged.
        """
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop publishing readings and wait briefly for termination.

        Args:
            None (None): This method operates on instance state only.

        Returns:
            None (None): This method signals termination and joins the worker
                thread when present.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
