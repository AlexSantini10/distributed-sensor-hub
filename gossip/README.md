# Module: gossip

## Responsibility
Best-effort dissemination of membership state across the cluster. The module publishes `GOSSIP_STATE` snapshots and merges inbound gossip into the local `PeerTable`.

## How It Works
- Each gossip round builds a snapshot from `peer_table.build_gossip_state()`.
- The snapshot is wrapped in a `GOSSIP_STATE` message and sent to known peers.
- On receipt, valid peer entries are parsed and merged through `peer_table.merge_gossip_state(...)`.
- Merge is last-write-wins on `status_ts_ms`: newer status information overrides older information, stale gossip is ignored.

## Intuition
- Gossip is used to spread the current membership view without requiring a central coordinator.
- Nodes do not need to hear directly from every other node all the time: status information can propagate hop by hop.
- Delivery is best-effort: a failed send to one peer does not abort the round.
- Convergence comes from repeated dissemination plus LWW merge semantics.

## Payload Shape
`GOSSIP_STATE` carries a JSON object like:

```json
{
  "membership": {
    "peers": [
      {
        "node_id": "node-b",
        "host": "10.0.0.2",
        "port": 9002,
        "status": "alive",
        "status_ts_ms": 1710000000000
      }
    ]
  }
}
```

## Inbound Validation
- `state.membership` must be an object when present.
- `state.membership.peers` must be a list.
- Each peer entry must contain valid `node_id`, `host`, `port`, `status`, and `status_ts_ms`.
- Malformed entries are skipped individually.
- Unknown status values are skipped.
- Gossip about the local node is ignored by `PeerTable.merge_gossip_state(...)`.

## Public API
### `publish_membership_gossip`
- Builds one `GOSSIP_STATE` snapshot and sends it to the provided peers.
- Send failures are logged at debug level and do not stop publication to other peers.

### `make_gossip_state_handler`
- Builds a configured inbound handler for `GOSSIP_STATE`.
- Parses membership entries, merges them into `PeerTable`, and optionally notifies `on_peer_discovered(peer)` for newly discovered peers.
- Callback failures are caught and logged without aborting the merge.

### `handle_gossip_state`
- Fallback handler used when gossip handling has not been wired for the node.
- Logs a warning instead of processing the message.

## Integration
- Outbound gossip is published by the runtime heartbeat loop.
- Inbound gossip is routed through protocol handlers to `make_gossip_state_handler(...)`.
- `gossip` does not own liveness computation; it only disseminates membership status already maintained by `membership` and `fd`.
