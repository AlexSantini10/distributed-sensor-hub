# sensors

## Purpose

The `sensors` module implements local sensor ingestion for the node runtime.

Its system role is to provide a strict **ingestion boundary** between sensor-specific data generation and downstream replicated-state processing. Providers emit `SensorReading` objects; handlers translate them into normalized state events without embedding networking, gossip, or merge logic.

## File Overview

- `__init__.py`: Public internal API for sensor contracts, default handler, manager, and built-in providers.
- `contracts.py`: Core contracts (`SensorReading`, `SensorProvider`, `SensorHandler`) defining lifecycle, payload shape, and timestamp semantics.
- `handler.py`: `QueueingSensorHandler`, which maps provider readings to canonical `SensorEvent` objects for state ingestion.
- `sensor_manager.py`: Configuration-driven provider construction, handler binding, provider registration, and start/stop orchestration.
- `providers/__init__.py`: Aggregates built-in provider classes.
- `providers/base_sensor.py`: Shared periodic provider runtime (threaded emission loop, lifecycle coordination, metadata construction, optional emission latency/jitter).
- `providers/numeric_sensor.py`: Uniform sampling in a numeric interval.
- `providers/boolean_sensor.py`: Bernoulli binary sampling.
- `providers/categorical_sensor.py`: Sampling from a finite categorical domain.
- `providers/incremental_sensor.py`: Stateful bounded relative drift process.
- `providers/trend_sensor.py`: Stateful trend plus bounded noise process.
- `providers/spike_sensor.py`: Baseline process with probabilistic spike events.
- `providers/wave_sensor.py`: Time-based sinusoidal process.
- `providers/noise_sensor.py`: Baseline with symmetric bounded noise.
- `providers/finite_test_sensor.py`: Deterministic finite sequence for bounded integration/testing scenarios.

## Main Dependencies

### Internal

- `utils.config` (`SensorConfig`, `SensorType`): typed configuration source for provider factory dispatch and parameter binding.
- `state.events` (`SensorEvent`): canonical event model consumed by downstream state workers.
- `utils.typing` (`JsonValue`, `SensorMetaDict`): shared JSON-compatible type contracts for payload and metadata fields.

### External (standard library)

- `threading`: provider lifecycle synchronization and background emission loops.
- `time`: wall-clock timestamps (`observed_at_ms`) and periodic scheduling.
- `random`: stochastic value generation and latency jitter sampling.
- `math`: waveform generation for sinusoidal providers.
- `dataclasses`, `typing`: immutable record and protocol-based contract definitions.

## High-Level Design

- **Core responsibilities**:
  - Define sensor-side contracts and lifecycle invariants.
  - Instantiate configured providers and bind them to a shared ingestion handler.
  - Preserve provider-observed timestamps and metadata across the ingestion boundary.

- **Main data flow**:
  - A provider generates a value and constructs `SensorReading(sensor_id, value, observed_at_ms, meta)`.
  - The provider pushes the reading to the configured handler.
  - `QueueingSensorHandler` converts the reading to `SensorEvent` and forwards it to the state-event sink.

- **Interactions with other modules**:
  - Upstream interaction: `utils.config` supplies validated sensor definitions.
  - Downstream interaction: `state` receives normalized events for LWW merge and replication dissemination via the rest of the runtime.
  - Non-interaction by design: providers remain decoupled from transport, gossip scheduling, and membership/failure-detection logic.
