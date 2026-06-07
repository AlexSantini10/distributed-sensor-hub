"""Provide the sensor subsystem public internal API.

Extension point for sensor integrations.

Purpose:
    The ``sensors`` package is the official extension point for local sensor
    ingestion. It defines how sensor data enters the application, independent of
    whether the source is a simulated generator, a hardware device, or a
    protocol adapter that translates an external device feed into local sensor
    readings.

Architecture:
    Sensor ingestion is split into two roles.

    - A ``SensorProvider`` produces ``SensorReading`` values.
    - A ``SensorHandler`` ingests those readings into the rest of the system.

    Providers push readings to handlers using a push-based model. The default
    runtime wiring uses ``QueueingSensorHandler`` to convert readings into
    normalized state events. State management, networking, gossip, heartbeat,
    and replication all remain downstream from this boundary.

How to extend:
    Implement ``SensorProvider`` for any new real sensor or adapter. The
    provider should own only source-specific concerns such as polling, device
    I/O, buffering, or vendor SDK callbacks. It must emit ``SensorReading``
    values to the configured ``SensorHandler`` and must not couple itself to
    networking, merge logic, gossip, or protocol routing.

    Minimal example:
        class MySensor:
            sensor_id = "device@0"
            def set_handler(self, handler: SensorHandler | None) -> None: ...
            def start(self) -> None: ...
            def stop(self) -> None: ...

Contracts:
    - ``SensorReading`` is the canonical data model for local ingestion.
    - ``sensor_id`` must be stable for the provider lifecycle.
    - ``observed_at_ms`` must be the original observation timestamp.
    - ``meta`` must remain JSON-compatible.
    - Providers may use background threads or callback-based device APIs, but
      handlers must be treated as thread-safe shared boundaries.

Lifecycle:
    Providers are started and stopped by ``SensorManager``. The default
    simulated providers run on daemon threads. Future providers may use another
    mechanism as long as they honor the same lifecycle and ingestion contracts.
"""

from .contracts import SensorHandler, SensorProvider, SensorReading
from .handler import QueueingSensorHandler
from .providers import (
    BaseSensor,
    BooleanSensor,
    CategoricalSensor,
    IncrementalSensor,
    NoiseSensor,
    NumericSensor,
    SpikeSensor,
    TrendSensor,
    WaveSensor,
)
from .sensor_manager import SensorManager

__all__ = [
    "BaseSensor",
    "BooleanSensor",
    "CategoricalSensor",
    "IncrementalSensor",
    "NoiseSensor",
    "NumericSensor",
    "QueueingSensorHandler",
    "SensorHandler",
    "SensorManager",
    "SensorProvider",
    "SensorReading",
    "SpikeSensor",
    "TrendSensor",
    "WaveSensor",
]
