# state

## Purpose

The `state` module implements the node-local replicated sensor state machine.
Its system role is to maintain **authoritative local winners** for each logical sensor under deterministic Last-Write-Wins (LWW) semantics, and to expose consistent snapshots/deltas for:

- inbound replication handlers (`SENSOR_UPDATE`, full sync, delta pull),
- outbound gossip replication (push/pull rounds),
- Web/API state observation.

## File Overview

- `state/events.py`: Defines canonical sensor-event normalization (`SensorEvent`) and a validated queue wrapper (`SensorEventQueue`) for local ingress.
- `state/policy.py`: Defines merge-policy abstractions and the default `LwwMergePolicy` based on `(ts_ms, origin)` ordering.
- `state/contracts.py`: Defines protocol-style interfaces (`RecordMergeStore`, `StateStoreLike`) used to decouple worker logic from concrete storage.
- `state/node_state_store.py`: Implements thread-safe storage of current winners, UI incremental updates, and bounded ordered replication deltas.
- `state/node_state_worker.py`: Runs the background ingestion/merge loop, applies local and remote updates, and exposes full/incremental read APIs.
- `state/__init__.py`: Exposes the module boundary and public contracts/policies.

## Main Dependencies

- `utils.typing`: Provides shared structural types (`NodeSnapshot`, replication delta types, JSON aliases) used across runtime/protocol boundaries.
- `threading` (stdlib): Ensures safe concurrent access to replicated state and supports background worker execution.
- `queue` (stdlib): Supports asynchronous sensor-event ingestion from producers.
- `state.policy`: Supplies pluggable conflict-resolution semantics; default is deterministic LWW.
- `protocol.handlers.state_sync` (internal consumer): Invokes state merge/read paths for full sync and delta-serving workflows.
- `runtime.sensor_update_publisher` (internal consumer): Drains replication deltas and computes per-peer pull cursors from state watermarks.
- `webapi.http_api` via `runtime.startup` (internal consumer): Reads full and incremental snapshots for monitoring endpoints.

## High-Level Design

- <u>Core responsibilities</u>:
  - Normalize heterogeneous event payloads before merge.
  - Maintain one winning record per logical `sensor_id`.
  - Resolve conflicts deterministically with LWW on `(timestamp, origin)`.
  - Provide separate incremental channels for UI consumption and replication.

- Data flow:
  - Local sensors emit events into `SensorEventQueue`.
  - `NodeStateWorker` consumes events and applies `merge_update(..., origin=self.node_id)`.
  - Remote updates are merged through the same merge path (`merge_update` / `merge_state`), preserving uniform conflict semantics.
  - Applied winners are materialized in:
    - full state map (`_state`),
    - UI incremental buffer (`_updates_ui`),
    - bounded ordered replication delta buffer (`_replication_deltas`).

- Interactions with other modules:
  - `protocol.handlers.state_sync` writes remote updates into the worker/store and requests deltas using timestamp cursors (`since_ts_ms`); if history is too old, state signals unavailability (`None`) so the protocol layer can trigger full sync.
  - `runtime.sensor_update_publisher` drains deltas for push dissemination and uses per-origin latest timestamps to request missing updates (pull).
  - `runtime.startup` wires the state worker as a shared dependency for networking, replication, and Web API snapshot providers.
