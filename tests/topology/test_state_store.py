"""Validate disseminated topology state merge and snapshot behavior."""

from __future__ import annotations

from topology.state import TopologyEntry, TopologyStateStore


def test_topology_state_store_merges_lww_per_node_entry() -> None:
    """Assert newer topology entries replace older ones for the same node id."""
    store = TopologyStateStore(self_node_id="node-a")
    store.set_local_neighbors(("node-b",))

    old = TopologyEntry(
        node_id="node-c",
        direct_neighbors=("node-a",),
        updated_at_ms=10,
    )
    newer = TopologyEntry(
        node_id="node-c",
        direct_neighbors=("node-a", "node-d"),
        updated_at_ms=11,
    )
    stale = TopologyEntry(
        node_id="node-c",
        direct_neighbors=("node-a",),
        updated_at_ms=9,
    )

    assert store.merge_entry(old) is True
    assert store.merge_entry(stale) is False
    assert store.merge_entry(newer) is True

    adjacency = store.get_adjacency_map()
    assert adjacency["node-c"] == ("node-a", "node-d")


def test_topology_state_store_updates_local_entry_on_connect_disconnect() -> None:
    """Assert local topology declaration changes when neighbors connect/disconnect."""
    store = TopologyStateStore(self_node_id="node-a")
    initial = store.set_local_neighbors(())
    assert initial.direct_neighbors == ()

    connected = store.mark_neighbor_connected("node-b")
    assert connected is not None
    assert connected.direct_neighbors == ("node-b",)
    assert connected.updated_at_ms > initial.updated_at_ms

    disconnected = store.mark_neighbor_disconnected("node-b")
    assert disconnected is not None
    assert disconnected.direct_neighbors == ()
    assert disconnected.updated_at_ms > connected.updated_at_ms


def test_topology_state_store_returns_deterministic_topology_snapshot() -> None:
    """Assert topology snapshots include adjacency and serialized entries."""
    store = TopologyStateStore(self_node_id="node-a")
    store.set_local_neighbors(("node-c", "node-b"))
    store.merge_entry(
        TopologyEntry(
            node_id="node-b",
            direct_neighbors=("node-a",),
            updated_at_ms=100,
        )
    )

    snapshot = store.topology_snapshot()
    assert snapshot["local_node_id"] == "node-a"
    assert snapshot["adjacency"] == {
        "node-a": ["node-b", "node-c"],
        "node-b": ["node-a"],
    }
    assert isinstance(snapshot["entries"], list)
    assert len(snapshot["entries"]) == 2
