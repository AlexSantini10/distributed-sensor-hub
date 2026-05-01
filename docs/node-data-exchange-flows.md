# Node Data Exchange Flows

This note summarizes when a node sends or requests data in the current implementation.

## Membership

### `JOIN_REQUEST` (send)
- Trigger: startup bootstrap toward configured bootstrap peers.
- Trigger: discovery of a new peer (`on_peer_discovered`) for reciprocal discovery.
- Mode: event-driven (startup + discovery).

### `PEER_LIST` (send)
- Trigger: received `JOIN_REQUEST`.
- Mode: request-response (event-driven).

### `GOSSIP_STATE` with membership fragment (send)
- Trigger: heartbeat round publication.
- Frequency: every `HEARTBEAT_INTERVAL_MS`.
- Mode: periodic.

### `PING` / `PONG`
- `PING` trigger: heartbeat round.
- `PONG` trigger: received `PING`.
- Mode: `PING` periodic, `PONG` event-driven.

## State Replication

### `SENSOR_UPDATE` push (send)
- Trigger: replication round when local deltas are available.
- Frequency: replication round every `GOSSIP_SYNC_INTERVAL_MS`.
- Targets: random subset of peers with status `alive` (fanout by `GOSSIP_PUSH_RATIO`, `GOSSIP_PUSH_MIN_PEERS`).
- Mode: periodic.

### `GET_DELTA` pull (request)
- Trigger: pull cadence reached.
- Cadence: every `GOSSIP_PULL_EVERY_ROUNDS` replication rounds.
- Targets: random subset of peers with status `alive` (fanout by `GOSSIP_PULL_RATIO`, `GOSSIP_PULL_MIN_PEERS`).
- Mode: periodic (cadenced).

### `SENSOR_UPDATE` delta serve (send)
- Trigger: received `GET_DELTA` and requested history is available.
- Mode: event-driven response.

### `DELTA_UNAVAILABLE` (send)
- Trigger: received `GET_DELTA` with stale cursor / unavailable history window.
- Mode: event-driven response.

### `FULL_SYNC_REQUEST` (request)
- Trigger: received `DELTA_UNAVAILABLE` (fallback path).
- Trigger: startup bootstrap flow also issues initial full-sync requests to bootstrap peers.
- Mode: event-driven + startup.

### `FULL_SYNC_RESPONSE` (send)
- Trigger: received `FULL_SYNC_REQUEST`.
- Payload: full state snapshot + membership snapshot.
- Mode: request-response (event-driven).

## Topology

### Topology dissemination
- No dedicated `GET_TOPOLOGY` request exists in peer-to-peer protocol.
- Topology is piggybacked in `GOSSIP_STATE`.
- Trigger: heartbeat gossip publication rounds.
- Frequency: every `HEARTBEAT_INTERVAL_MS`.
- Mode: periodic dissemination.

### Local topology updates
- Trigger: local connectivity/status changes (peer connected/disconnected, status transitions).
- Dissemination: propagated on next gossip round.
- Mode: event-driven local write + periodic dissemination.

## Observability (Read-only)

### HTTP introspection endpoints (`/api/introspection*`)
- Trigger: external client polling/request.
- Mode: request-response, read-only.
- Note: does not participate in cluster coordination writes.
