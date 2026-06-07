# networking

## Purpose

The `networking` module provides the node-to-node **transport layer** for protocol messages over TCP.

Its role in the overall system is to isolate connection management and length-prefixed framing from protocol semantics, enabling upper layers to exchange typed messages while preserving transport-level concerns (session lifecycle, retries, and bounded frame handling) within one module.

## File Overview

- `tcp_client.py`  
  Implements outbound peer transport: one worker per peer, FIFO enqueue per peer, framed send (`4-byte length + payload`), reconnect backoff, idle connection probing, and optional delay/loss simulation for experiments.
- `tcp_server.py`  
  Implements inbound transport: listening socket, per-connection frame reads, frame-size validation, protocol message decoding, and dispatch to an injected handler interface.
- `__init__.py`  
  Defines module-level scope and the framing-oriented transport boundary exposed by this package.

## Main Dependencies

- `protocol.message.Message` (internal): provides canonical decode of inbound frame payloads before dispatch.
- `utils.typing.SupportsToBytes` (internal): enforces that outbound messages expose `to_bytes()` for protocol-owned serialization.
- Python standard library `socket`, `struct`, `threading` (external): implements TCP I/O, fixed-size frame header encoding, and concurrent connection/session management.
- Python standard library `queue`, `selectors`, `time` (external): supports per-peer buffered outbound flow, non-blocking liveness checks, and timeout/backoff control.
- Python standard library `dataclasses`, `typing`/`Protocol` (external): defines transport contracts and immutable peer descriptors used across runtime integration points.

## High-Level Design

- **Core responsibilities**
- Maintain inbound and outbound TCP connectivity for inter-node messaging.
- Apply and validate a common length-prefixed framing contract.
- Preserve per-peer send ordering under healthy connections and recover from disconnects via bounded retry.
- Forward only decoded protocol messages to upstream dispatch logic without interpreting message semantics.

- Main data flow
- Outbound path: upper module submits typed message -> message serialized via `to_bytes()` -> payload framed with big-endian length prefix -> frame sent on peer socket (or queued until reconnection).
- Inbound path: server accepts connection -> reads exact frame header and payload -> rejects oversized/invalid frames -> decodes payload into `Message` -> dispatches to protocol handler.
- Failure path: connection/read/send errors trigger socket teardown and reconnect loop (client side) or connection termination (server side); queued outbound payloads are best-effort.

- Interactions with other modules
- `runtime.networking` instantiates and wires `TcpClient`/`TcpServer` into node startup and shutdown lifecycle.
- `protocol` consumes inbound decoded messages through dispatcher callbacks and supplies outbound serializable message objects.
- Higher-level subsystems (`membership`, `gossip`, replicated state handlers) use this module indirectly through protocol send/receive paths, relying on <u>eventual delivery attempts rather than transport-level reliability guarantees</u>.

## Inbound Backpressure and Limits (`TcpServer`)

`tcp_server.py` enforces bounded concurrency to prevent saturation under overload.

- **Connection limiting**
  - Active inbound connections are capped by `MAX_CONNECTIONS`.
  - When the cap is reached, newly accepted connections are immediately closed (load shedding).

- **Bounded execution model**
  - Connection handlers run on a `ThreadPoolExecutor`.
  - Worker concurrency is capped by `MAX_WORKERS` (no unbounded thread-per-connection growth).

- **Timeouts and slow peers**
  - `SOCKET_TIMEOUT` is applied to accept/read loops so slow or silent clients do not block indefinitely.
  - Framing remains length-prefixed (`4-byte length + payload`) with max-frame checks.

- **Shutdown behavior**
  - Stop accepting new connections.
  - Close tracked active sockets.
  - Shutdown worker pool and clear tracking state safely.

- **Operational signals**
  - Logs include connection accepted, rejected (limit reached), and closed events.

### Trade-off

The current strategy prefers predictable resource bounds over queueing:
excess inbound connections are rejected early instead of being buffered indefinitely.
