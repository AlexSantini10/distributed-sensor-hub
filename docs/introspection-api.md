# Introspection API (`introspection/v1`)

This project now exposes reusable, read-only introspection surfaces for monitoring, tests, scripts, and debugging tools.

## Endpoints

- `GET /api/introspection`: aggregate cluster introspection snapshot
- `GET /api/introspection/topology`: merged global topology view
- `GET /api/introspection/membership`: per-node membership/health view
- `GET /api/introspection/state`: replicated sensor-state snapshot
- `GET /api/introspection/events`: recent protocol/control-plane events
- `GET /api/introspection/metrics`: replication/gossip metrics

Legacy endpoints (`/api/state`, `/api/updates`, `/api/membership`, `/api/topology`) remain read-only and supported.

## Contract guarantees

- `schema_version` is stable (`"introspection/v1"`).
- `generated_at_ms` is an epoch-millisecond generation timestamp.
- Topology is based on each node's merged global topology view (`topology.state.TopologyStateStore`), not only direct transport links.
- `membership.peers[*].phi` is exposed only for directly observed peers.
- For indirect-only peers, `membership.peers[*].phi` is `null`.
- All surfaces are read-only.

## Schemas

### Aggregate

```json
{
  "schema_version": "introspection/v1",
  "generated_at_ms": 0,
  "cluster": {
    "topology": {
      "local_node_id": "string",
      "adjacency": {"node_id": ["neighbor_id"]},
      "entries": [
        {"node_id": "string", "direct_neighbors": ["string"], "updated_at_ms": 0}
      ]
    },
    "membership": {
      "local_node_id": "string",
      "peers": [
        {
          "peer_id": "string",
          "host": "string",
          "port": 0,
          "status": "alive|suspected|dead",
          "phi": 0.0,
          "last_heartbeat_ts_ms": 0,
          "sample_count": 0,
          "sample_window_size": 0,
          "status_transition_ts_ms": 0,
          "direct_status": "alive|suspected|dead|unknown",
          "evidence_status": "active|stale|unknown",
          "display_status": "alive_direct|alive_indirect|suspected|dead|unknown",
          "last_evidence_ts_ms": 0,
          "last_evidence_source": "string",
          "direct_observed": true
        }
      ]
    },
    "sensor_state": {
      "record_count": 0,
      "records": [
        {
          "global_sensor_id": "origin:sensor_id",
          "sensor_id": "sensor_id",
          "origin": "origin",
          "ts_ms": 0,
          "value": null,
          "meta": {"unit": null, "period_ms": null}
        }
      ]
    },
    "events": {
      "count": 0,
      "items": [
        {
          "ts_ms": 0,
          "event_type": "string",
          "category": "control_plane",
          "sender_id": "string",
          "target_id": "string",
          "details": {}
        }
      ]
    },
    "metrics": {
      "counters": {
        "gossip_messages_received_total": 0,
        "gossip_messages_sent_total": 0,
        "sensor_updates_applied_total": 0,
        "sensor_updates_pushed_total": 0,
        "get_delta_requests_received_total": 0,
        "get_delta_requests_sent_total": 0,
        "get_delta_unavailable_total": 0,
        "full_sync_requests_received_total": 0,
        "full_sync_requests_sent_total": 0,
        "full_sync_responses_received_total": 0,
        "full_sync_responses_sent_total": 0,
        "replication_rounds_total": 0
      },
      "state_replication": {
        "next_seq": 0,
        "last_read_seq": 0,
        "oldest_retained_seq": 0,
        "newest_retained_seq": 0,
        "retained_delta_count": 0,
        "latest_seq_by_origin": {"node_id": 0}
      }
    }
  }
}
```

## Example responses

### `GET /api/introspection/membership`

```json
{
  "schema_version": "introspection/v1",
  "generated_at_ms": 1713720000000,
  "membership": {
    "local_node_id": "node-1",
    "peers": [
      {
        "peer_id": "node-2",
        "host": "10.0.0.2",
        "port": 9002,
        "status": "alive",
        "phi": 0.203,
        "last_heartbeat_ts_ms": 1713720000000,
        "sample_count": 8,
        "sample_window_size": 128,
        "status_transition_ts_ms": 1713720000000,
        "direct_status": "alive",
        "evidence_status": "active",
        "display_status": "alive_direct",
        "last_evidence_ts_ms": 1713720000000,
        "last_evidence_source": "direct_heartbeat",
        "direct_observed": true
      },
      {
        "peer_id": "node-3",
        "host": "10.0.0.3",
        "port": 9003,
        "status": "alive",
        "phi": null,
        "last_heartbeat_ts_ms": 0,
        "sample_count": 0,
        "sample_window_size": 128,
        "status_transition_ts_ms": 1713720000100,
        "direct_status": "unknown",
        "evidence_status": "active",
        "display_status": "alive_indirect",
        "last_evidence_ts_ms": 1713720000100,
        "last_evidence_source": "gossip_status",
        "direct_observed": false
      }
    ]
  }
}
```

### `GET /api/introspection/events`

```json
{
  "schema_version": "introspection/v1",
  "generated_at_ms": 1713720000500,
  "events": {
    "count": 2,
    "items": [
      {
        "ts_ms": 1713720000300,
        "event_type": "get_delta_requested",
        "category": "control_plane",
        "sender_id": "node-1",
        "target_id": "node-2",
        "details": {"from_seq": 44}
      },
      {
        "ts_ms": 1713720000400,
        "event_type": "sensor_update_received",
        "category": "control_plane",
        "sender_id": "node-2",
        "target_id": "node-1",
        "details": {"sensor_id": "temperature", "ts_ms": 1713720000399, "applied": true, "source": "pull"}
      }
    ]
  }
}
```
