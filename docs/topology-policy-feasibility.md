# Topology Policy Feasibility Assessment (Task 0)

## Scope and objective

This note assesses whether the current architecture can support an injectable `TopologyPolicy` without changing current runtime behavior.

The assessment is based on the current code in:

- `runtime/networking.py`
- `runtime/heartbeat.py`
- `runtime/startup.py`
- `runtime/sensor_update_publisher.py`
- `protocol/setup.py`
- `protocol/handlers/membership.py`
- `protocol/handlers/state_sync.py`
- `gossip/handlers.py`
- `membership/peer_table.py`
- `networking/tcp_client.py`

## Feasibility conclusion

The refactor is **feasible** with dependency inversion and without breaking existing behavior.

Current architecture already provides two strong foundations:

- Membership state is centralized in `PeerTable`.
- Outbound transport lifecycle is centralized in `TcpClient`.

However, topology decisions are currently spread across runtime and protocol callbacks, and one data model (`PeerTable`) currently mixes endpoint identity and direct-liveness state. This is manageable, but Task 1 should isolate decision boundaries before introducing non-full-mesh policies.

## Current responsibilities and coupling

### Membership tracking

- `PeerTable` owns known peers, endpoint metadata, and phi-based liveness (`membership/peer_table.py`).
- Membership convergence comes from join, peer-list, gossip, and full-sync handlers.

### Active TCP connection management

- `TcpClient` owns per-peer workers, connect/reconnect/backoff, and queue draining (`networking/tcp_client.py`).
- Registration of peers into `TcpClient` happens from runtime flows (`runtime/networking.py`) and publisher fallback (`runtime/sensor_update_publisher.py`).

### Gossip dissemination

- Heartbeat runtime publishes membership gossip once per round (`runtime/heartbeat.py` + `gossip/publisher.py`).
- Gossip merge path can discover new peers and trigger discovery callback (`gossip/handlers.py`).

### Heartbeat and direct failure detection

- Heartbeat sender sends `PING` to all peers returned by `PeerTable.snapshot()` (`runtime/heartbeat.py`).
- Phi evaluation runs over all peers in `PeerTable` (`membership/peer_table.py`).

### Recovery and full sync

- Startup sends `FULL_SYNC_REQUEST` to bootstrap peers (`runtime/startup.py`).
- `DELTA_UNAVAILABLE` handler immediately requests full sync from sender (`protocol/handlers/state_sync.py`).
- Full-sync response merges membership and can trigger discovery callback for newly seen peers.

### Join handling

- `JOIN_REQUEST` upserts peer, then replies with `PEER_LIST` (`protocol/handlers/membership.py`).
- Newly inserted peers trigger the shared discovery callback.

## Concept separability check

### 1. Known peers

Explicit and centralized:

- `PeerTable._peers` is the local known-membership set.

### 2. Connected peers

Implicit and transport-local:

- `TcpClient._workers` represents registered outbound connection workers.
- There is no explicit read model that cleanly exposes "currently connected" vs "known but disconnected".

### 3. Direct liveness

Explicit but broad:

- Phi/heartbeat liveness is tracked in `PeerTable` for every known peer.
- Heartbeat sender probes all known peers, not a policy-selected neighbor subset.

### 4. Indirect observability

Implicit through gossip state:

- `merge_gossip_state` applies remote status/timestamp using LWW.
- Indirect observations are merged into the same peer object that also carries direct detector state.

### Where concepts are mixed

- `membership.peer.Peer` combines endpoint identity with liveness state.
- `PeerTable` merges endpoint updates, direct detector state, and gossip-derived status in one structure.
- Runtime loops (heartbeat and replication) iterate membership snapshot directly, assuming "known peer" is also a communication target.

## Topology decision points in current code

### Who to connect to

- `runtime/networking.py`: discovery callback always calls `registry.ensure_peer(...)`.
- `runtime/networking.py`: bootstrap peers are always added via `build_bootstrap_peers(...)`.
- `runtime/sensor_update_publisher.py`: on `KeyError`, publisher auto-adds peer before resend.

### When to reconnect

- `networking/tcp_client.py`: `_PeerWorker._run()` reconnect loop with bounded backoff.
- Reconnect policy is transport-level only (not topology-aware).

### Whether to disconnect

- Manual only via `TcpClient.remove_peer(...)` or `stop()`.
- No topology-driven prune flow currently exists.

### How to react to newly discovered peers

- `protocol/handlers/membership.py`, `gossip/handlers.py`, and `protocol/handlers/state_sync.py` all call `on_peer_discovered(...)` for new peers.
- `runtime/networking.py` callback currently performs:
  - outbound peer registration
  - immediate reciprocal `JOIN_REQUEST`

### Centralization status

Partially centralized:

- Discovery event source is centralized through a shared callback.
- Decision behavior is still hardcoded in runtime callback logic plus publisher fallback path.

## DIP readiness for `TopologyPolicy`

### Suitable interface boundary

Best boundary is between peer-discovery/membership events and transport mutations:

- Inputs: membership snapshot, transport registration snapshot, event cause (`bootstrap`, `discovered`, `tick`, `send_failure`, `fd_transition`), local node id.
- Outputs: declarative actions such as:
  - `ensure_connected(peer_id, host, port)`
  - `request_join(peer_id)`
  - `disconnect(peer_id)`
  - `probe(peer_id)`
  - `gossip_to(peer_id)` / `replicate_to(peer_id)` (optional later)

### Suitable context object

A topology context should be immutable and read-only, at minimum:

- local node id
- known peers (from `PeerTable.snapshot()`)
- currently registered outbound peers (from `TcpClient`)
- optional liveness summary (status/phi/status timestamp)
- event metadata (reason/source peer)

### Adapter and factory insertion points

- Runtime composition: `setup_node_networking(...)` is the right factory entry for injecting a policy implementation.
- Protocol wiring: `setup_protocol(...)` already receives one callback and can route discovery events into a policy adapter.
- Heartbeat loop and publisher loop can later consume policy-selected target sets instead of full snapshot broadcast.

### Circular dependency and hidden coupling risks

- Avoid policy calling `PeerTable` mutators directly; it should return actions only.
- Avoid policy depending on transport internals (`_PeerWorker`); provide read-only adapter methods.
- Avoid cross-calls where transport failure directly mutates membership semantics.

## Concrete blockers and risks

1. Hardcoded peer selection in runtime loops:
- Heartbeat probes and gossip target all known peers.
- Sensor replication targets all known peers.

2. Topology logic mixed with socket-execution paths:
- Discovery callback performs both decision and execution (register + send join).
- Publisher fallback auto-adds peers on send path.

3. Membership and connectivity are stored separately but not modeled as separate domain concepts:
- `PeerTable` contains known membership.
- `TcpClient` contains registered outbound workers.
- No explicit reconciler currently models desired vs actual connectivity.

4. Full-mesh assumptions remain implicit:
- Discovery callback immediately joins every new peer.
- Periodic heartbeat and gossip run over full membership snapshot.

5. Direct FD currently applies to all known peers:
- This is correct for current behavior but will need policy scoping for partial topologies.

6. Join flow is tightly coupled to immediate connection attempts:
- New peer discovery triggers immediate `ensure_peer` and `JOIN_REQUEST`.

## Minimal preparatory changes required before Task 1

No runtime behavior change is required in Task 0.

Recommended minimal prep for Task 1:

1. Introduce a topology-decision interface that returns declarative actions (no socket side effects inside policy).
2. Add a small transport read adapter exposing registered peers, to separate known-membership from connectivity state.
3. Route all "new peer discovered" handling through one runtime reconciler function/object so decision and execution can be split cleanly.
4. Keep current full-mesh behavior as the default policy implementation to preserve invariants.

## Invariants to preserve during refactor

- Keep `PeerTable` as the single source of known membership and liveness.
- Preserve current join/bootstrap/full-sync semantics and message ordering expectations.
- Keep `TcpClient` reconnection/backoff behavior unchanged.
- Preserve best-effort error swallowing/logging behavior in heartbeat, gossip, and publisher loops.
- Do not auto-insert unknown peers from heartbeat-only traffic (current heartbeat handler behavior).

## Task 1 insertion points (recommended)

- Primary policy injection: `runtime/networking.setup_node_networking(...)`.
- Event ingress: `on_peer_discovered(...)` callback used by membership, gossip, and full-sync handlers.
- Periodic reconciliation hook: heartbeat loop tick (after snapshot, before fanout).
- Optional send-failure hook: publisher fallback path for controlled connect-on-demand.
