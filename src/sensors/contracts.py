"""Define the sensor-ingestion contracts exposed by the sensors package.

Extension point for sensor integrations.

This module defines the public internal API that all sensor integrations must
target. A sensor provider is responsible only for producing readings and
managing its own lifecycle. A sensor handler is responsible only for ingesting
those readings into the rest of the system.

Architecture:
    Providers push ``SensorReading`` instances to a ``SensorHandler``. The
    handler forms the ingestion boundary between sensor-specific code and the
    replicated-state pipeline. The rest of the application depends on these
    abstractions instead of concrete simulated sensor classes.

Data flow:
    The flow is push-based. Providers actively emit readings when they observe
    them, typically from a provider-owned background thread, callback, or device
    event loop.

Lifecycle:
    Providers must support ``start()`` and ``stop()``. ``start()`` should be
    safe to call once a handler has been attached. ``stop()`` must make a
    best-effort attempt to stop background work and return promptly. Handlers
    must be thread-safe because providers may call them from background threads.

Contracts:
    - ``sensor_id`` must remain stable for the lifetime of the provider.
    - ``observed_at_ms`` must represent the observation timestamp in Unix
      milliseconds and must not be rewritten by the handler.
    - ``meta`` must remain JSON-compatible and should include only transport-safe
      descriptive context such as units or sampling period.
    - Providers must not depend on networking, gossip, or merge/state logic.

Example:
    A provider can implement ``SensorProvider`` and call
    ``handler.handle(SensorReading(...))`` whenever a real device interrupt or
    polling loop yields a new sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from utils.typing import JsonValue, SensorMetaDict


@dataclass(frozen=True, slots=True)
class SensorReading:
    """Represent one sensor observation crossing the ingestion boundary.

    Extension point for sensor integrations.

    Attributes:
        sensor_id (str): Stable logical sensor identifier for the reading source.
        value (JsonValue): JSON-compatible sensor payload observed by the provider.
        observed_at_ms (int): Unix timestamp in milliseconds for the observation.
        meta (SensorMetaDict): JSON-compatible descriptive metadata propagated with
            the reading.
    """

    sensor_id: str
    value: JsonValue
    observed_at_ms: int
    meta: SensorMetaDict


@runtime_checkable
class SensorHandler(Protocol):
    """Define the ingestion boundary that accepts provider readings.

    Extension point for sensor integrations.

    Implementations must be thread-safe because providers may call ``handle``
    from background threads. Handlers must preserve the observation timestamp
    and payload semantics supplied by the provider.

    Example:
        ``handler.handle(SensorReading(sensor_id="temp@0", value=21.4,
        observed_at_ms=1710000000000, meta={"unit": "C", "period_ms": 5000}))``
    """

    def handle(self, reading: SensorReading) -> None:
        """Ingest one provider reading.

        Args:
            reading (SensorReading): Observed reading produced by a provider.

        Returns:
            None: This method ingests the reading in place.
        """
        ...


@runtime_checkable
class SensorProvider(Protocol):
    """Define the lifecycle and emission contract for sensor providers.

    Extension point for sensor integrations.

    Providers own sensor-specific polling, interrupt handling, buffering, and
    device communication. They must not publish directly to networking or state
    systems. Instead, they push ``SensorReading`` values to the configured
    ``SensorHandler``.

    Threading model:
        Providers may emit from background threads or device callbacks. Calls to
        ``set_handler`` are expected during startup before ``start()``. Handlers
        must therefore tolerate concurrent ``handle`` calls after startup.
    """

    sensor_id: str

    def set_handler(self, handler: SensorHandler | None) -> None:
        """Attach or clear the ingestion handler for future readings.

        Args:
            handler (SensorHandler | None): Handler that will receive future
                readings, or ``None`` to clear the current handler.

        Returns:
            None: This method updates the provider's ingestion target.
        """
        ...

    def start(self) -> None:
        """Start producing readings.

        Returns:
            None: This method starts provider-owned work.
        """
        ...

    def stop(self) -> None:
        """Stop producing readings.

        Returns:
            None: This method stops provider-owned work.
        """
        ...
