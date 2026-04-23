# Node Services Inventory

This document lists the runtime services that exist inside one node, what each
service is responsible for, and how services interact.

## Why This Exists

When working on one subsystem (for example `fd/heartbeat.py`), it is easy to
forget where that subsystem is used in the full node lifecycle. This page is a
single reference for that mapping.

## Node Service Map

| Service | Main module(s) | What it does | Primary inputs | Primary outputs |
|---|---|---|---|---|
| Lifecycle orchestration | `runtime/application.py`, `runtime/startup.py` | Starts/stops all node subsystems in dependency-safe order | Config + logger | Running node services |
| Config loading | `utils/config.py` | Parses and validates env configuration (`NODE_ID`, ports, sensors, gossip/fd params, topology policy) | Environment variables | Immutable `Config` |
| Transport (TCP) | `networking/tcp_client.py`, `networking/tcp_server.py` | Handles outbound/inbound TCP message delivery | Encoded protocol messages | Message send/receive |
| Protocol dispatch + handlers | `runtime/protocol_assembly.py`, `protocol/handlers/*` | Routes inbound messages by type and applies membership/state actions | Decoded protocol messages | Mutations on membership/state + protocol responses |
| Membership table | `membership/peer_table.py` | Maintains authoritative local view of peers and liveness metadata | Join/discovery events, gossip merges, direct evidence | Membership snapshots and status transitions |
| Failure detection (phi-accrual) | `fd/heartbeat.py`, `fd/phi_estimator.py` (used by `PeerTable`) | Computes `phi` from heartbeat timing and classifies peers (`alive`/`suspected`/`dead`) | Heartbeat observations + periodic evaluation clock | Detector-local liveness signal consumed by membership |
| Heartbeat runtime | `runtime/heartbeat.py` | Periodic loop: evaluate FD, publish membership gossip, send `PING` probes | `PeerTable` snapshot, connected peers | `PING` traffic + membership updates + gossip publication |
| Membership gossip | `gossip/publisher.py`, `gossip/handlers.py` | Disseminates and merges membership state using `GOSSIP_STATE` | Membership snapshots and inbound gossip | Eventual membership convergence |
| Sensor providers | `sensors/sensor_manager.py`, `sensors/providers/*`, `sensors/handler.py` | Generates local sensor readings and pushes them into the local event queue | Sensor config + periodic timers | Local sensor events |
| Local state worker/store | `state/node_state_worker.py`, `state/node_state_store.py` | Applies LWW merge `(ts_ms, origin)`, keeps winners, builds UI and replication snapshots | Local sensor events + inbound state updates | State snapshots + replication delta stream |
| Sensor replication runtime | `runtime/sensor_update_publisher.py`, `protocol/handlers/state_sync.py` | Periodic push/pull (`SENSOR_UPDATE`, `GET_DELTA`) + full-sync fallback | Local replication deltas + peer availability | Cross-node sensor-state dissemination |
| Pull window classification | `runtime/pull_response_tracker.py` | Classifies inbound updates as pull responses vs unsolicited push traffic | Outbound `GET_DELTA` requests + inbound seq observations | Classification hints + pull cursor tracking |
| Topology policy + state | `topology/policy.py`, `topology/full_mesh.py`, `topology/state.py` | Chooses outbound connect targets and tracks disseminated adjacency | Known peers + bootstrap peers + connectivity events | Connection decisions + topology snapshots |
| Introspection aggregation | `introspection/service.py` | Aggregates cluster snapshot (topology, membership, sensor state, events, metrics) | Providers from state/membership/topology + event stores | Unified introspection payload |
| Web API (read-only) | `webapi/http_api.py` | Exposes HTTP endpoints (`/api/state`, `/api/membership`, `/api/introspection`, ...) | Snapshot providers | JSON for UI/tests/tools |
| Browser dashboard | `web/app.js` | Polls Web API and renders topology/state/timeline cards | Introspection HTTP responses | Human-readable observability UI |

## Three Planes In One Node

### Control Plane

- Membership (`PeerTable`) and discovery (`JOIN_REQUEST`, `PEER_LIST`)
- Failure detection (phi-accrual) driven by heartbeat evidence
- Membership dissemination (`GOSSIP_STATE`)
- Topology connectivity decisions

### Data Plane (Sensor State)

- Local sensor generation
- Local LWW state merge/store
- Periodic push-pull replication (`SENSOR_UPDATE`, `GET_DELTA`)
- Full-sync requests/responses for catch-up when needed

### Observability Plane

- Introspection event + metric stores
- Cluster snapshot aggregation
- Read-only HTTP API
- Web dashboard rendering

## Service Dependencies (Who Uses What)

| Consumer | Uses | Purpose |
|---|---|---|
| `NodeApplication` | runtime startup helpers | Build and start/stop all node services in order |
| Runtime networking | topology policy | Choose outbound connection targets |
| Runtime networking | protocol assembly | Bind dispatcher and handlers |
| Protocol handlers | `PeerTable` | Apply membership/liveness updates |
| `PeerTable` | `HeartbeatMonitor` (`fd`) | Compute and track phi-accrual state |
| `HeartbeatSender` | `PeerTable.evaluate_failure_detector()` | Trigger periodic phi evaluation and status transitions |
| `HeartbeatSender` | gossip publisher | Disseminate membership snapshots |
| Sensor providers | queueing sensor handler | Feed local events to state worker queue |
| Sensor replication runtime | state worker deltas + `PeerTable` snapshot | Push/pull sensor state to alive peers |
| Introspection service | state + membership + topology providers | Build unified cluster snapshot |
| Web API | introspection/snapshot providers | Expose read-only HTTP endpoints |
| Browser dashboard | Web API | Render observability views (read-only) |

## Startup Order (Operationally Important)

`NodeApplication.start()` starts services in this order:

1. State worker
2. Networking stack + protocol dispatcher
3. Membership bootstrap (`JOIN_REQUEST` + initial `FULL_SYNC_REQUEST`)
4. Heartbeat runtime (FD eval + gossip + `PING`)
5. Sensors + sensor replication publisher
6. Web API + introspection service

This order ensures inbound network messages can be applied before heavy traffic
starts, and observability only starts when node internals are ready.

## Common Confusions (And Correct Mapping)

- `gossip` is for **membership/liveness state**, not sensor values.
- Sensor values replicate through the **push-pull replication runtime**
  (`SENSOR_UPDATE`, `GET_DELTA`, `FULL_SYNC_*`).
- `fd` computes local suspicion (`phi`); `membership` translates that into
  replicated node status metadata.
- Web API/UI are observers: they do not mutate replicated state.

## Where HeartbeatMonitor Actually Lives

`HeartbeatMonitor` is implemented in `fd/heartbeat.py` but instantiated and
owned by `membership.PeerTable`. The runtime heartbeat loop does not implement
the phi math itself; it triggers periodic evaluation through `PeerTable`.
