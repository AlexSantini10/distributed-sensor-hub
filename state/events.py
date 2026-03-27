from dataclasses import dataclass
from queue import Queue
from typing import Any


@dataclass
class SensorEvent:
    sensor_id: str
    value: Any
    ts_ms: int
    meta: dict

    @staticmethod
    def from_dict(event: dict) -> "SensorEvent":
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

        return SensorEvent(sensor_id=sensor_id, value=value, ts_ms=ts_ms, meta=meta)

    @staticmethod
    def from_any(event) -> "SensorEvent":
        if isinstance(event, SensorEvent):
            return event
        if isinstance(event, dict):
            return SensorEvent.from_dict(event)
        raise ValueError(f"Unsupported sensor event type: {type(event).__name__}")


class SensorEventQueue:
    """Queue wrapper that normalizes incoming raw events to SensorEvent."""

    def __init__(self):
        self._queue = Queue()

    def put(self, event) -> None:
        self._queue.put(SensorEvent.from_any(event))

    def get(self, timeout=None) -> SensorEvent:
        return self._queue.get(timeout=timeout)
