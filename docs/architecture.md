# Architecture

## Scope

Distributed Sensor Hub is a decentralized runtime where each node executes the same stack:

- sensor production
- local state merge/store
- peer membership + failure detection
- TCP protocol transport/dispatch
- HTTP read API

No coordinator is required for normal operation.

## Module responsibilities

| Module | Responsibility | Reference |
|---|---|---|
| `runtime` | Composition root, startup/shutdown ordering, background loops | [runtime/README.md](../runtime/README.md) |
| `protocol` | Message types/contracts, codec, dispatcher, protocol handlers | [protocol/README.md](../protocol/README.md) |
| `networking` | Length-prefixed TCP transport, reconnect/send queues | [networking/README.md](../networking/README.md) |
| `membership` | Peer table, liveness metadata, merge of membership views | [membership/README.md](../membership/README.md) |
| `fd` | Phi-accrual computation and detector-local status | [fd/README.md](../fd/README.md) |
| `gossip` | Best-effort dissemination of membership snapshots | [gossip/README.md](../gossip/README.md) |
| `state` | Authoritative local winners and replication deltas | [state/README.md](../state/README.md) |
| `sensors` | Provider lifecycle and conversion to canonical events | [sensors/README.md](../sensors/README.md) |
| `topology` | Policy-driven connection target selection | [topology/README.md](../topology/README.md) |
| `webapi` | Read-only HTTP observation endpoints | [webapi/README.md](../webapi/README.md) |

Dependency overview diagram: [module-dependencies.svg](module-dependencies.svg)
PlantUML source: [module-dependencies.puml](module-dependencies.puml)

## Runtime sequence

1. Load config and logging.
2. Start state worker first.
3. Wire networking + protocol dispatcher + peer table.
4. Seed bootstrap peers and send `JOIN_REQUEST`.
5. Request initial `FULL_SYNC`.
6. Start heartbeat loop (`PING/PONG` + membership gossip + phi evaluation).
7. Start sensor providers and periodic push/pull replication.
8. Expose HTTP snapshots via Web API.

## Protocol surface

- Membership discovery: `JOIN_REQUEST`, `PEER_LIST`
- Liveness: `PING`, `PONG`
- State replication: `SENSOR_UPDATE`
- Membership dissemination: `GOSSIP_STATE`
- Incremental sync: `GET_DELTA`, `DELTA_UNAVAILABLE`
- Full sync: `FULL_SYNC_REQUEST`, `FULL_SYNC_RESPONSE`
- Reserved: `ERROR`, `ACK` (registered placeholders)

## Consistency and liveness model

- State convergence uses **LWW** ordering `(ts_ms, origin)`.
- Incremental replication cursors use monotonic per-node `seq` values (transport only, not conflict resolution).
- Replication is periodic push/pull and best-effort.
- Membership convergence uses gossip merge with _last-write-wins on `status_ts_ms`_.
- Liveness suspicion is local phi-accrual (`alive`, `suspected`, `dead`) and then disseminated.

## Design notes

- Separate membership data from sensor-state data.
- Keep sensor providers decoupled from networking/protocol.
- Keep transport concerns (`networking`) isolated from protocol semantics (`protocol`).
- Maintain independent incremental streams for UI and replication consumers.
