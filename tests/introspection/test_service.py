"""Validate reusable cluster introspection service snapshots."""

from typing import cast

from introspection.service import (
    ClusterIntrospectionService,
    ControlPlaneEventStore,
    ReplicationGossipMetricsStore,
)
from utils.typing import JsonObject


def test_membership_snapshot_hides_phi_for_indirect_peers() -> None:
    """Assert non-direct peers expose ``phi=None`` in introspection snapshots."""
    events = ControlPlaneEventStore(max_events=8)
    metrics = ReplicationGossipMetricsStore()
    service = ClusterIntrospectionService(
        state_provider=lambda: {"node-a": {}},
        membership_provider=lambda: {
            "local_node_id": "node-a",
            "peers": [
                {
                    "peer_id": "node-b",
                    "host": "10.0.0.2",
                    "port": 9002,
                    "status": "alive",
                    "phi": 0.5,
                    "last_heartbeat_ts_ms": 10,
                    "sample_count": 2,
                    "sample_window_size": 16,
                    "status_transition_ts_ms": 10,
                    "direct_status": "unknown",
                    "evidence_status": "active",
                    "display_status": "alive_indirect",
                    "last_evidence_ts_ms": 10,
                    "last_evidence_source": "gossip_status",
                    "direct_observed": False,
                }
            ],
        },
        topology_provider=lambda: {"local_node_id": "node-a", "adjacency": {}, "entries": []},
        replication_stats_provider=lambda: {"next_seq": 4},
        control_plane_events=events,
        replication_metrics=metrics,
    )

    membership = cast(JsonObject, service.membership_snapshot().get("membership", {}))
    peers = cast(list[JsonObject], membership.get("peers", []))
    assert membership["local_node_id"] == "node-a"
    assert peers[0]["phi"] is None


def test_cluster_snapshot_includes_all_surfaces() -> None:
    """Assert aggregate snapshot exposes topology/state/events/metrics surfaces."""
    events = ControlPlaneEventStore(max_events=8)
    events.add_event(
        event_type="sensor_update_sent",
        category="control_plane",
        sender_id="node-a",
        target_id="node-b",
        details={"sensor_id": "temp"},
    )
    metrics = ReplicationGossipMetricsStore()
    metrics.increment("replication_rounds_total")
    service = ClusterIntrospectionService(
        state_provider=lambda: {
            "node-a": {
                "node-a:temp": {
                    "value": 42,
                    "ts_ms": 100,
                    "origin": "node-a",
                    "meta": {"unit": "C", "period_ms": 1000},
                }
            }
        },
        membership_provider=lambda: {"local_node_id": "node-a", "peers": []},
        topology_provider=lambda: {
            "local_node_id": "node-a",
            "adjacency": {"node-a": ["node-b"], "node-b": ["node-a"]},
            "entries": [
                {"node_id": "node-a", "direct_neighbors": ["node-b"], "updated_at_ms": 100},
                {"node_id": "node-b", "direct_neighbors": ["node-a"], "updated_at_ms": 90},
            ],
        },
        replication_stats_provider=lambda: {"next_seq": 7, "retained_delta_count": 3},
        control_plane_events=events,
        replication_metrics=metrics,
    )

    cluster = cast(JsonObject, service.cluster_snapshot().get("cluster", {}))
    topology = cast(JsonObject, cluster.get("topology", {}))
    adjacency = cast(JsonObject, topology.get("adjacency", {}))
    sensor_state = cast(JsonObject, cluster.get("sensor_state", {}))
    events = cast(JsonObject, cluster.get("events", {}))
    metrics = cast(JsonObject, cluster.get("metrics", {}))
    counters = cast(JsonObject, metrics.get("counters", {}))
    state_replication = cast(JsonObject, metrics.get("state_replication", {}))

    assert adjacency["node-b"] == ["node-a"]
    assert sensor_state["record_count"] == 1
    assert events["count"] == 1
    assert counters["replication_rounds_total"] == 1
    assert state_replication["next_seq"] == 7
