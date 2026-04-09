# Architecture and Design

## Table of contents

- [System overview](#system-overview)
- [Runtime lifecycle](#runtime-lifecycle)
- [Main subsystems](#main-subsystems)
- [Protocol surface](#protocol-surface)
- [Technologies used](#technologies-used)
- [Design choices](#design-choices)
- [Distributed systems concepts applied](#distributed-systems-concepts-applied)
- [Data flow (current)](#data-flow-current)

## System overview

The system consists of independent nodes running the same software stack. Nodes discover peers through bootstrap addresses and membership exchange, maintain a local view of peer liveness, replicate sensor updates across the cluster, and expose HTTP endpoints for observing replicated state and membership.

Each node is autonomous and includes the full application stack:

- sensor producers
- local state worker and LWW store
- TCP server and outbound TCP client
- protocol dispatcher and handlers
- membership and failure-detection state
- HTTP API for monitoring

## Runtime lifecycle

The node startup sequence is orchestrated by `node.py` and `runtime/application.py`.

The current lifecycle is:

1. Load environment-backed configuration and initialize logging.
2. Start the `NodeStateWorker` before any network or sensor traffic is accepted.
3. Assemble the TCP client/server, protocol dispatcher, and shared `PeerTable`.
4. Seed the peer table with configured bootstrap peers and send initial `JOIN_REQUEST` messages.
5. Request `FULL_SYNC` from bootstrap peers to catch up with existing cluster state.
6. Start the heartbeat sender, which also evaluates phi-accrual liveness and publishes membership gossip.
7. Start local sensor providers and the `SensorUpdatePublisher`.
8. Start the Web API exposing state, updates, and membership snapshots.

## Main subsystems

### Sensors (`sensors/`)

Sensors are periodic daemon threads that emit readings into a shared event queue. The project currently includes numeric, boolean, noise, wave, trend, spike, categorical, and incremental sensors.

Events are normalized through `state/events.py`:

- `SensorEvent`: typed event payload (`sensor_id`, `value`, `ts_ms`, `meta`)
- `SensorEventQueue`: queue wrapper that accepts raw dict events and stores normalized `SensorEvent` objects

### State replication (`state/`)

State logic is split into dedicated components:

- `NodeStateWorker`: background orchestrator thread; consumes sensor events, validates/normalizes inputs, logs decisions, and delegates state mutations
- `NodeStateStore`: thread-safe state container with standard operations (`merge_record`, `upsert`, `remove`, `clear`) and snapshot APIs
- `SensorMeta` / `SensorRecord`: typed dataclasses for internal state records

`NodeStateStore` maintains Last-Write-Wins semantics using `(ts_ms, origin)` and keeps two independent incremental update buffers:

- UI/Web API updates
- outbound replication updates

`SensorUpdatePublisher` drains ordered replication deltas and broadcasts `SENSOR_UPDATE` messages to known peers. Only local-origin winners are re-published, which avoids immediate rebroadcast loops.

### Membership (`membership/`)

`PeerTable` is the in-memory registry of known peers. It stores endpoint metadata, liveness metadata, and phi-accrual-derived status transitions.

The membership subsystem currently supports:

- peer discovery through `JOIN_REQUEST` and `PEER_LIST`
- transitive expansion when newly discovered peers are announced
- liveness tracking through `PING` and `PONG`
- status transitions across `alive`, `suspected`, and `dead`
- membership gossip snapshots exchanged through `GOSSIP_STATE`

### Protocol (`protocol/`)

All node-to-node traffic is wrapped in a common `Message` envelope:

```text
Message {
    msg_type  : MessageType
    sender_id : str
    payload   : dict
    timestamp : int
}
```

The dispatcher maps each `MessageType` to a dedicated handler. Handler wiring happens during runtime setup so protocol messages can mutate membership, update liveness, merge replicated state, and serve synchronization requests.

### Networking (`networking/`)

`TcpServer` handles inbound framed messages, while `TcpClient` maintains per-peer outbound connections with reconnection support. Messages use length-prefixed framing over TCP to preserve boundaries on a byte stream.

The runtime networking setup also adapts bootstrap peers into outbound client peers and registers newly discovered peers dynamically.

### Failure detection (`fd/`)

Failure detection is implemented with a phi-accrual monitor that tracks heartbeat intervals per peer. The heartbeat loop periodically:

- evaluates phi values for all known peers
- applies status transitions in the `PeerTable`
- publishes membership gossip
- sends one `PING` per known peer

Incoming `PING` and `PONG` messages refresh heartbeat observations and can move a peer back to `alive`.

### Web API (`webapi/`)

The HTTP API exposes:

- `GET /api/state`
- `GET /api/updates`
- `GET /api/membership`

All endpoints are read-only and CORS-enabled for browser-based polling clients and test tooling.

## Protocol surface

The protocol currently includes these major message families:

| Message family | Message types | Purpose |
|---------------|---------------|---------|
| Membership discovery | `JOIN_REQUEST`, `PEER_LIST` | Advertise endpoints and exchange known peers |
| Liveness | `PING`, `PONG` | Record heartbeat observations and drive phi-based status |
| State replication | `SENSOR_UPDATE` | Replicate individual winning sensor records |
| Membership gossip | `GOSSIP_STATE` | Disseminate membership status snapshots |
| Full synchronization | `FULL_SYNC_REQUEST`, `FULL_SYNC_RESPONSE` | Bootstrap or recover full state and membership |
| Incremental catch-up | `GET_DELTA`, `DELTA_UNAVAILABLE` | Request deltas since a timestamp or fall back to full sync |
| Control / reserved | `ERROR`, `ACK` | Reserved for protocol-level signaling |

## Technologies used

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.14 | Main implementation language |
| `python-dotenv` | >= 1.0 | Environment-driven configuration |
| `pytest` | >= 9.0 | Unit and integration testing |
| Docker / Docker Compose | n/a | Containerized deployment |
| `socket` | stdlib | TCP transport |
| `threading` / `queue` | stdlib | Concurrency primitives |
| `http.server` | stdlib | REST API server |

## Design choices

### No centralized coordinator

Every node is autonomous. There is no leader or broker, which removes a central dependency from the data path.

### LWW CRDT for state replication

The system uses Last-Write-Wins conflict resolution to keep sensor state convergent without consensus.

The winner ordering is based on `(ts_ms, origin)`, where the timestamp is the primary key and the origin acts as a deterministic tie-breaker.

### Environment-variable configuration

Node identity, network endpoints, bootstrap peers, and sensors are configured through environment variables so the same image can serve different node roles.

### Two independent update streams

`NodeStateStore` separates updates intended for the Web API from updates intended for replication, preventing one consumer from starving the other.

### Decoupled state and event models

State mutation rules are isolated inside `NodeStateStore`, while input normalization is isolated in `SensorEvent`/`SensorEventQueue`. This keeps `NodeStateWorker` focused on orchestration and reduces coupling between sensors, state storage, and replication.

### TCP with length-prefix framing

Messages are framed with a 4-byte big-endian length header, which provides reliable boundaries over a stream-oriented transport.

### Full-sync first, delta-friendly replication

A joining node requests `FULL_SYNC` from bootstrap peers after the initial membership join. In steady state, replication is driven by incremental deltas. If a delta cursor is too old, the protocol can fall back to `DELTA_UNAVAILABLE` followed by a new `FULL_SYNC_REQUEST`.

### Membership and state are synchronized separately

The project keeps peer membership/liveness data separate from replicated sensor state. This reduces coupling between cluster topology concerns and application-level data convergence.

## Distributed systems concepts applied

| Concept | Current usage |
|---------|---------------|
| Gossip / Epidemic dissemination | Membership propagation through `JOIN_REQUEST` and `PEER_LIST` |
| CRDT (LWW register) | Conflict-free state merge in `NodeStateStore` |
| Eventual consistency | Sensor state converges asynchronously across nodes |
| Peer-to-peer communication | Symmetric TCP communication without hierarchy |
| Decentralized membership | Peer discovery without a directory server |
| Failure detection | Phi-accrual heartbeat tracking over periodic `PING` / `PONG` |
| Fault-tolerant networking | Reconnection and keepalive support in the TCP client |
| State partitioning | Sensor updates carry origin information to avoid ambiguity |
| Multi-threaded concurrency | Explicit locking and queue-based worker coordination |

## Data flow (current)

1. Sensor threads emit readings via `SensorManager` callback into `SensorEventQueue`.
2. `NodeStateWorker` consumes events and applies merges through the store merge contract (`merge_record(...)`).
3. `SensorUpdatePublisher` consumes replication deltas and sends `SENSOR_UPDATE` to known peers.
4. Incoming remote `SENSOR_UPDATE` messages are validated by protocol handlers and merged through `NodeStateWorker.merge_update(...)`.
5. Heartbeat rounds evaluate phi, gossip the current membership view, and send `PING` probes to peers.
6. `PING` / `PONG` handlers refresh heartbeat observations and update peer status when needed.
7. New or recovering nodes request `FULL_SYNC`; peers respond with current state and membership snapshots.
8. Web API clients read full state, incremental updates, and membership snapshots through HTTP polling.
