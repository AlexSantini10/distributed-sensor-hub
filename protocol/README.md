# protocol

## Purpose

The `protocol` module defines the node-to-node message layer for the distributed sensor hub.  
Its role is to provide a single, validated path for:

- **wire-format contracts** (message types, envelope fields, payload schemas),
- message serialization/deserialization at the transport boundary,
- deterministic dispatch from decoded messages to protocol handlers,
- assembly of membership, heartbeat, gossip, and state-sync handlers into one runtime dispatcher.

In the overall system, this module is the boundary between `networking` (TCP transport) and domain modules (`membership`, `gossip`, `state`).

## File Overview

- `message_types.py`: Enumerates all protocol message categories used for membership, liveness, replication, pull/full synchronization, and control.
- `contracts.py`: Centralizes canonical wire keys and constants shared by encoder/decoder and handlers.
- `messages.py`: Defines typed payload models and the validated `Message` envelope, including schema checks at construction and decode time.
- `message.py`: Backward-compatible alias exposing the canonical `Message` type.
- `codec.py`: Implements JSON/UTF-8 encoding and decoding between typed messages and transport bytes.
- `factory.py`: Provides canonical builders for outbound messages; enforces construction through typed payload contracts.
- `dispatcher.py`: Registers per-type handlers and routes validated inbound messages to the corresponding callback.
- `handlers/membership.py`: Handles `JOIN_REQUEST` and `PEER_LIST`; updates membership view and emits peer-discovery callbacks.
- `handlers/heartbeat.py`: Handles `PING`/`PONG`; records liveness evidence and status transitions in membership tracking.
- `handlers/state_sync.py`: Handles `SENSOR_UPDATE`, `GET_DELTA`, `DELTA_UNAVAILABLE`, `FULL_SYNC_REQUEST`, and `FULL_SYNC_RESPONSE`; performs merge/update orchestration and fallback from delta to full sync.
- `handlers/__init__.py`: Re-exports handler factories and default placeholder handlers.
- `setup.py`: Composes dispatcher, peer table, and handler wiring for runtime initialization.
- `__init__.py`: Exposes the module’s stable public API (types, dispatcher, and builders).

## Main Dependencies

- `membership.peer_table`, `membership.peer`: Maintain peer membership/liveness state consumed and updated by protocol handlers.
- `gossip.handlers`: Supplies the `GOSSIP_STATE` merge handler integrated during protocol setup.
- `state` worker interfaces (`StateWorkerLike`, `ReplicationDeltaSourceLike`): Provide merge, snapshot, and delta retrieval operations for replication handlers.
- `networking` sender abstraction (`SenderLike`): Decouples protocol handlers from concrete TCP client implementation.
- `utils.typing`: Defines JSON and protocol-facing structural types used across message and handler contracts.
- `utils.logging`: Provides per-node structured logging inside handler execution paths.
- Python standard library (`dataclasses`, `enum`, `json`, `time`, `typing`): Supports immutable typed payloads, deterministic enums, wire serialization, and timestamps.

## High-Level Design

Core responsibilities:

- Validate protocol envelopes and payloads before domain-side processing.
- Preserve a stable mapping between wire-level message identifiers and typed payload contracts.
- Route each validated message to a single registered handler.
- Orchestrate replication control flow for <u>incremental delta sync</u> and full-state fallback.

Main data flow:

1. Transport receives bytes and decodes JSON through `codec.py`.
2. `message_from_dict` reconstructs a typed `Message` and enforces schema validity.
3. `MessageDispatcher` selects the handler by `MessageType`.
4. Handler applies side effects in membership/state subsystems and may emit response messages via `factory.py`.
5. Outbound messages are encoded back to bytes through the same codec path.

Interactions with other modules:

- With `networking`: consumes incoming decoded messages and emits outbound protocol messages via injected send callbacks.
- With `membership`: updates peer table from joins, peer lists, heartbeats, gossip evidence, and sync-derived observations.
- With `gossip`: reuses gossip parsing/merge logic for membership convergence.
- With `state`: applies sensor updates, serves deltas, serves full snapshots, and merges remote snapshots for eventual consistency.

Current implementation note:

- `ERROR` and `ACK` message handling is registered but intentionally raises `NotImplementedError` in `setup.py`.
