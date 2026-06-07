# membership

## Purpose

The `membership` module maintains the node-local view of known peers and their liveness metadata.

Its role in the overall system is to act as the **authoritative local membership state** used by protocol handlers, heartbeat/failure-detection loops, and gossip dissemination to achieve eventual convergence of peer status information.

## File Overview

- `peer_table.py`  
  Implements `PeerTable`, the thread-safe membership store and coordination point for peer insert/update/removal, failure-detector integration, membership snapshot generation, and merge logic for inbound membership/gossip views.
- `peer.py`  
  Defines the `Peer` record (node identity, endpoint, liveness) and compatibility accessors used by runtime and protocol code.
- `liveness.py`  
  Defines `NodeLiveness`, the mutable liveness aggregate (heartbeat, phi, status, timestamps, and evidence metadata) attached to each peer.
- `status.py`  
  Defines `NodeStatus` (`alive`, `suspected`, `dead`) and stable wire conversion helpers for serialized membership state.
- `results.py`  
  Defines immutable result dataclasses that encode outcomes of membership mutations and failure-detection-driven transitions.
- `__init__.py`  
  Provides the module-level responsibility declaration for membership primitives and view maintenance.

## Main Dependencies

### Internal

- `fd.heartbeat.HeartbeatMonitor`  
  Provides phi-accrual tracking and per-peer liveness evaluation consumed by `PeerTable`.
- `fd.status.FailureStatus`  
  Supplies detector-local status classes that are mapped into membership-domain `NodeStatus` values.
- `utils.typing` (`JsonObject`, membership snapshot types)  
  Defines typed contracts for serialized gossip payloads and read-only membership snapshots.

### External

- Python standard library (`threading`, `time`, `dataclasses`, `enum`, `typing`, `collections.abc`)  
  Supports concurrency control, timing, immutable/structured records, and type-safe container interfaces.

## High-Level Design

- **Core responsibilities**
- Maintain a lock-protected peer table with atomic membership operations.
- Combine direct heartbeat evidence and phi-accrual outputs into local liveness state.
- Merge remote membership information while preserving deterministic conflict handling.
- Expose snapshot-oriented read paths (not live mutable references) for other subsystems.

- Main data flow
- Local updates: protocol/runtime events upsert peers and record direct/indirect evidence.
- Failure detection: `HeartbeatMonitor` observations/evaluations update phi and local status transitions.
- Dissemination path: outbound gossip is built from a serialized membership snapshot.
- Convergence path: inbound membership/gossip payloads are merged with <u>last-write-wins on `status_ts_ms`</u> for replicated status fields.

- Interactions with other modules
- `protocol.handlers.membership` and `protocol.handlers.heartbeat` mutate membership from inbound control messages.
- `protocol.handlers.state_sync` applies membership merges during full-state exchange and records indirect evidence.
- `gossip` reads snapshots and submits inbound gossip state for merge.
- `runtime` seeds bootstrap peers, triggers periodic failure-detector evaluation, and consumes membership snapshots for monitoring/peer selection.
