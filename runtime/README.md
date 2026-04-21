# runtime

## Purpose

The `runtime` module is the node-level orchestration layer. It assembles and coordinates transport, protocol dispatch, membership management, state replication, sensor ingestion, and monitoring services into one executable runtime.

In the overall system, it acts as the **composition boundary** between domain subsystems (state, membership, gossip, protocol, sensors) and the process lifecycle (startup, steady state, shutdown).

## File Overview

- `application.py`: defines `NodeApplication`, the lifecycle container that starts and stops subsystems in dependency-safe order.
- `startup.py`: provides startup helpers that instantiate and connect state worker, networking stack, membership bootstrap, sensor pipeline, heartbeat loop, and Web API server.
- `networking.py`: builds runtime networking context (TCP client/server, dispatcher, peer table), applies topology policy to peer registration, and performs membership bootstrap messaging.
- `heartbeat.py`: runs periodic heartbeat rounds (`PING`) and membership gossip publication; triggers phi-accrual evaluation through `PeerTable`.
- `sensor_update_publisher.py`: executes periodic <u>push-pull replication</u> rounds, sending `SENSOR_UPDATE` deltas and `GET_DELTA` requests to sampled alive peers.
- `pull_response_tracker.py`: tracks short-lived pull windows to classify inbound updates as pull responses versus unsolicited push traffic.
- `bootstrap.py`: configures early process logging, global exception hooks, and optional log truncation before full runtime initialization.
- `__init__.py`: package-level module descriptor for runtime assembly responsibilities.

## Main Dependencies

### Internal

- `state.node_state_worker`: authoritative local state worker; provides merge, snapshot, and delta interfaces consumed by runtime threads.
- `networking.tcp_client` and `networking.tcp_server`: outbound/inbound TCP transport primitives used by protocol messaging.
- `runtime.protocol_assembly` and `protocol.factory`: protocol dispatcher wiring and message construction (`JOIN_REQUEST`, `PING`, `SENSOR_UPDATE`, `GET_DELTA`, `FULL_SYNC_REQUEST`).
- `membership.peer_table`: shared membership/failure-detection state used by bootstrap, heartbeat, and peer selection.
- `sensors.sensor_manager` and `sensors.handler`: local sensor event production and queue-based ingestion into state processing.
- `gossip.publisher`: membership dissemination during heartbeat rounds.
- `topology.resolver` and `topology.policy`: topology-aware peer connection decisions during bootstrap and discovery.
- `webapi.http_api`: read-only HTTP exposure of state/update/membership snapshots.
- `utils.config` and `utils.typing`: runtime configuration contract and protocol-like type interfaces.

### External

- Python standard library (`threading`, `time`, `dataclasses`, `http.server`, `logging`): concurrency control, timing, structured context objects, lightweight HTTP serving, and process-level diagnostics.

## High-Level Design

### Core Responsibilities

- Enforce deterministic startup/shutdown sequencing across concurrent subsystems.
- Maintain continuous node participation in membership and liveness detection.
- Drive eventual state dissemination via periodic push-pull rounds.
- Bridge local sensor production to replicated state and external observability.

### Main Data Flow

1. Local sensors emit events to `SensorEventQueue`.
2. `NodeStateWorker` consumes events and materializes LWW state plus replication deltas.
3. `SensorUpdatePublisher` periodically samples alive peers and disseminates deltas (`SENSOR_UPDATE`), with scheduled pull rounds (`GET_DELTA`).
4. Incoming protocol messages are dispatched through the runtime-configured `MessageDispatcher` into membership/state handlers.
5. `HeartbeatSender` periodically evaluates phi-accrual status, gossips membership state, and sends direct heartbeat probes.
6. `WebAPIServer` exposes snapshot views for monitoring without mutating replicated state.

### Interactions With Other Modules

- With `protocol`: runtime provides transport/send callbacks, state worker hooks, and peer-discovery callbacks used by handlers.
- With `membership` and `gossip`: runtime seeds peers, updates peer connectivity, and performs periodic membership dissemination.
- With `state`: runtime delegates all merge and snapshot semantics to the state worker/store layer.
- With `sensors`: runtime converts sensor stream output into queued events for deterministic state ingestion.
- With `webapi`: runtime exports read paths for system observability while keeping replication logic internal.
