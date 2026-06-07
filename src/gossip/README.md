# gossip

## Purpose
The `gossip` module implements **best-effort dissemination** of membership liveness metadata using `GOSSIP_STATE` messages.

Its system role is to propagate peer status observations between nodes and to support eventual membership convergence at cluster scale. The module does not compute failure-detector outputs; it only transports and merges membership state produced by other components.

## File Overview
- `publisher.py`: Builds one membership snapshot per round and broadcasts it to known peers via the transport sender callback.
- `handlers.py`: Validates inbound gossip payloads, parses peer entries, and merges them into `PeerTable` with timestamp-based conflict resolution.
- `__init__.py`: Exposes the public module surface (`publish_membership_gossip`, `make_gossip_state_handler`, fallback handler).

## Main Dependencies
- `membership.peer_table.PeerTable`: Source of outbound gossip snapshots and merge target for inbound membership updates.
- `membership.peer.Peer` and `membership.status.NodeStatus`: Typed representation of peer endpoints and liveness states.
- `protocol.factory.build_gossip_state`: Constructs protocol-compliant `GOSSIP_STATE` messages for transmission.
- `protocol.message.Message` and `protocol.messages.GossipStatePayload`: Typed inbound envelope/payload used for safe handler validation.
- `runtime.heartbeat.HeartbeatSender` (integration point): Invokes periodic gossip publication during heartbeat rounds.
- Python standard library (`time`, `collections.abc`): Timestamping parsed liveness evidence and typing callback/iterable contracts.

## High-Level Design
- **Core responsibilities**:
  - Serialize local membership view into `GOSSIP_STATE`.
  - Disseminate snapshots in a best-effort broadcast pattern.
  - Validate and merge received snapshots into local membership state.
- Main data flow:
  - Outbound path: `PeerTable.build_gossip_state()` -> `build_gossip_state(...)` -> send to each peer.
  - Inbound path: dispatcher routes `GOSSIP_STATE` -> handler validates payload shape -> valid peer records are converted and merged through `PeerTable.merge_gossip_state(...)`.
  - Merge policy: <u>last-write-wins on `status_ts_ms`</u>; stale status updates are ignored.
- Interactions with other modules:
  - `runtime` triggers periodic dissemination.
  - `protocol` performs message routing and payload typing.
  - `membership` owns authoritative local storage and merge semantics.
  - Optional discovery callback notifies runtime when gossip reveals previously unknown peers.
