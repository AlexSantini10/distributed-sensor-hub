"""Define ingestion handlers that bridge sensor providers to state ingestion.

Extension point for sensor integrations.

Handlers convert provider-owned ``SensorReading`` values into the normalized
event shape consumed by the rest of the application. This module exists so
providers remain independent from queueing, replicated state, and networking.
"""

from __future__ import annotations

from collections.abc import Callable

from sensors.contracts import SensorHandler, SensorReading
from state.events import SensorEvent


class QueueingSensorHandler(SensorHandler):
    """Bridge push-based sensor readings into the normalized state-event queue.

    Extension point for sensor integrations.

    This handler is the default ingestion boundary used by the runtime. It is
    intentionally small: it preserves provider timestamps and metadata while
    converting a reading into the canonical ``SensorEvent`` model expected by
    the state worker.

    Attributes:
        event_sink (Callable[[SensorEvent], None]): Thread-safe sink that accepts
            normalized sensor events.
    """

    def __init__(self, event_sink: Callable[[SensorEvent], None]) -> None:
        """Initialize the queueing ingestion handler.

        Args:
            event_sink (Callable[[SensorEvent], None]): Sink that receives
                normalized events.

        Returns:
            None: This constructor stores the ingestion sink.
        """
        self.event_sink = event_sink

    def handle(self, reading: SensorReading) -> None:
        """Convert one provider reading into a normalized sensor event.

        Args:
            reading (SensorReading): Reading produced by a sensor provider.

        Returns:
            None: This method forwards the normalized event to ``event_sink``.
        """
        self.event_sink(
            SensorEvent(
                sensor_id=reading.sensor_id,
                value=reading.value,
                ts_ms=reading.observed_at_ms,
                meta=reading.meta,
            )
        )
