"""Normalize sensor event payloads before they enter replicated state.

Responsibilities:
    - Define the canonical event shape consumed by state workers.
    - Validate externally supplied event dictionaries before LWW ingestion.
    - Provide a queue wrapper that guarantees dequeued items are ``SensorEvent`` instances.
"""

from dataclasses import dataclass
from queue import Queue

from utils.typing import JsonObject, JsonValue, SensorEventDict, SensorMetaDict


@dataclass
class SensorEvent:
    """Represent one logical sensor sample ready for LWW merging.

    Attributes:
        sensor_id (str): Logical sensor identifier that competes in the LWW register.
        value (JsonValue): Sample payload associated with the sensor update.
        ts_ms (int): Millisecond timestamp used as the primary LWW ordering key.
        meta (SensorMetaDict): Sensor metadata propagated with the sample for downstream consumers.
    """

    sensor_id: str
    value: JsonValue
    ts_ms: int
    meta: SensorMetaDict

    @staticmethod
    def from_dict(event: JsonObject | SensorEventDict) -> "SensorEvent":
        """Build a normalized sensor event from a mapping payload.

        Args:
            event (JsonObject | SensorEventDict): Raw event mapping that must provide
                ``sensor_id`` and ``ts_ms``.

        Returns:
            SensorEvent: Validated event instance with normalized metadata.

        Raises:
            ValueError: If the payload does not contain a valid sensor identifier or timestamp.
        """
        sensor_id = event.get("sensor_id")
        value = event.get("value")
        ts_ms = event.get("ts_ms")
        meta = event.get("meta", {})

        if not isinstance(sensor_id, str) or sensor_id == "":
            raise ValueError("Invalid sensor event: missing/invalid sensor_id")
        if not isinstance(ts_ms, int):
            raise ValueError("Invalid sensor event: missing/invalid ts_ms")
        if not isinstance(meta, dict):
            meta = {}

        normalized_meta: SensorMetaDict = {
            "unit": meta.get("unit"),
            "period_ms": meta.get("period_ms"),
        }
        return SensorEvent(
            sensor_id=sensor_id,
            value=value,
            ts_ms=ts_ms,
            meta=normalized_meta,
        )

    @staticmethod
    def from_any(event: object) -> "SensorEvent":
        """Convert a supported event representation into a canonical event.

        Args:
            event (object): Event object supplied by sensors, tests, or networking code.

        Returns:
            SensorEvent: Canonical event instance accepted by the state pipeline.

        Raises:
            ValueError: If the value is neither a ``SensorEvent`` nor a supported mapping.
        """
        if isinstance(event, SensorEvent):
            return event
        if isinstance(event, dict):
            return SensorEvent.from_dict(event)
        raise ValueError(f"Unsupported sensor event type: {type(event).__name__}")


class SensorEventQueue:
    """Serialize queue ingress into validated ``SensorEvent`` objects.

    Attributes:
        _queue (Queue[SensorEvent]): FIFO buffer whose contents are guaranteed to be
            normalized events.
    """

    def __init__(self) -> None:
        """Initialize an empty normalized event queue.

        Returns:
            None: This constructor does not return a value.
        """
        self._queue: Queue[SensorEvent] = Queue()

    def put(self, event: object) -> None:
        """Enqueue one normalized sensor event.

        Args:
            event (object): Raw event value accepted by ``SensorEvent.from_any``.

        Returns:
            None: This method enqueues the event in place.

        Raises:
            ValueError: If the supplied event cannot be normalized.
        """
        self._queue.put(SensorEvent.from_any(event))

    def get(self, timeout: float | None = None) -> SensorEvent:
        """Dequeue one normalized sensor event.

        Args:
            timeout (float | None): Timeout forwarded to the underlying queue implementation.

        Returns:
            SensorEvent: Next normalized event in FIFO order.
        """
        return self._queue.get(timeout=timeout)
