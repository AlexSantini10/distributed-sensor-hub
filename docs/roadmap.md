# Roadmap and Missing Pieces

This document collects the parts that are still incomplete or intentionally deferred in the current implementation.

## Current limitations

- Failure detection is only partially present: peer metadata includes `phi`, heartbeat timestamps, and status fields, but the active heartbeat loop is not complete.
- `GOSSIP_STATE` anti-entropy is not implemented yet.
- `FULL_SYNC_REQUEST` and `FULL_SYNC_RESPONSE` are still placeholders.
- Gossip cycle control is not implemented, so redundant propagation may occur in denser topologies.
- State is kept in memory only; there is no persistence layer or snapshot recovery.
- Inter-node communication is unauthenticated and unencrypted.
- The provided Docker examples typically rely on a single bootstrap peer per node.

## Planned improvements

### Membership and failure detection

- Complete the `PING` / `PONG` heartbeat loop.
- Use phi-accrual values to move peers across `alive`, `suspected`, and `dead`.

### Anti-entropy and synchronization

- Implement periodic `GOSSIP_STATE` exchange between peers.
- Add `FULL_SYNC` support so a new or recovering node can retrieve current cluster state.
- Add bounded gossip behavior such as hop count or seen-set tracking.

### Durability

- Add a write-ahead log or periodic snapshots.
- Support node restart recovery without requiring state rebuild from scratch.

### Security

- Introduce TLS for node-to-node communication.
- Add lightweight authentication for peer admission and message acceptance.

### Operability

- Improve metrics and observability.
- Support more dynamic runtime topology changes, including cleaner join/leave flows.
