"""Validate thread-safe peer-table membership contracts."""

import threading
import time

from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus


def test_upsert_peer_success() -> None:
    """Assert that inserting a new remote peer succeeds with a typed outcome."""
    table = PeerTable(self_node_id="node-1")

    result = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    assert result.peer_id == "node-2"
    assert result.changed is True
    assert result.inserted is True
    assert result.previous_status is None
    assert result.new_status is NodeStatus.ALIVE
    assert result.should_gossip is True
    assert result.reason == "inserted"
    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "127.0.0.1"
    assert stored.port == 9001


def test_upsert_peer_idempotent() -> None:
    """Assert that inserting the same endpoint twice preserves one entry."""
    table = PeerTable(self_node_id="node-1")

    first = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    second = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    assert first.inserted is True
    assert second.changed is False
    assert second.inserted is False
    assert second.previous_status is NodeStatus.ALIVE
    assert second.new_status is NodeStatus.ALIVE
    assert second.should_gossip is False
    assert second.reason == "unchanged"
    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"


def test_upsert_self_peer_ignored() -> None:
    """Assert that a node never stores itself in the peer table."""
    table = PeerTable(self_node_id="node-1")

    result = table.upsert_peer(node_id="node-1", host="127.0.0.1", port=9000)

    assert result.changed is False
    assert result.inserted is False
    assert result.previous_status is None
    assert result.new_status is None
    assert result.should_gossip is False
    assert result.reason == "ignored_self"
    assert table.get_peer("node-1") is None
    assert table.snapshot() == ()


def test_mark_alive_existing_peer() -> None:
    """Assert that heartbeat updates refresh status for known peers."""
    table = PeerTable(self_node_id="node-1")

    inserted = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    assert inserted.peer is not None
    table.mark_suspected("node-2", phi=7.5)

    old_ts = inserted.peer.last_heartbeat
    new_ts = old_ts + 10.0

    result = table.mark_alive("node-2", heartbeat_at=new_ts)

    assert result.peer_id == "node-2"
    assert result.changed is True
    assert result.heartbeat_advanced is True
    assert result.phi_updated is True
    assert result.should_gossip is True
    assert result.status.changed is True
    assert result.status.previous_status is NodeStatus.SUSPECTED
    assert result.status.new_status is NodeStatus.ALIVE
    updated = table.get_peer("node-2")
    assert updated is not None
    assert updated.last_heartbeat == new_ts
    assert updated.status is NodeStatus.ALIVE
    assert updated.phi == 0.0


def test_mark_suspected_exposes_status_transition() -> None:
    """Assert that suspicion updates describe the liveness transition explicitly."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    result = table.mark_suspected("node-2", phi=7.5)

    assert result.changed is True
    assert result.heartbeat_advanced is False
    assert result.phi_updated is True
    assert result.should_gossip is True
    assert result.status.changed is True
    assert result.status.previous_status is NodeStatus.ALIVE
    assert result.status.new_status is NodeStatus.SUSPECTED
    assert result.reason == "marked_suspected"


def test_mark_alive_unknown_peer_noop() -> None:
    """Assert that heartbeat updates do not create unknown peers."""
    table = PeerTable(self_node_id="node-1")

    result = table.mark_alive("node-unknown", heartbeat_at=time.time())

    assert result.changed is False
    assert result.status.changed is False
    assert result.status.previous_status is None
    assert result.status.new_status is None
    assert result.reason == "peer_not_found"
    assert table.get_peer("node-unknown") is None
    assert table.snapshot() == ()


def test_snapshot_returns_copies() -> None:
    """Assert that callers cannot mutate live membership state through snapshots."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    snapshot = list(table.snapshot())
    snapshot[0].host = "mutated"
    snapshot[0].status = NodeStatus.SUSPECTED

    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "127.0.0.1"
    assert stored.status is NodeStatus.ALIVE


def test_merge_membership_view_integrates_new_peers_only() -> None:
    """Assert that membership-view merges add only previously unknown peers."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    merge = table.merge_membership_view(
        [
            Peer.new("node-2", "127.0.0.1", 9001),
            Peer.new("node-3", "127.0.0.1", 9002),
            Peer.new("node-1", "127.0.0.1", 9000),
        ]
    )

    ids = {p.node_id for p in table.snapshot()}
    assert ids == {"node-2", "node-3"}
    assert merge.changed is True
    assert merge.merged_entries == 1
    assert merge.ignored_entries == 1
    assert [p.node_id for p in merge.new_peers] == ["node-3"]
    assert merge.updated_peers == ()
    assert merge.should_gossip is True


def test_merge_membership_view_preserves_liveness_state() -> None:
    """Assert that endpoint merges do not reset suspicion metadata."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    table.mark_suspected("node-2", phi=12.0)

    result = table.merge_membership_view([Peer.new("node-2", "10.0.0.2", 9002)])

    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "10.0.0.2"
    assert stored.port == 9002
    assert stored.status is NodeStatus.SUSPECTED
    assert stored.phi == 12.0
    assert result.changed is True
    assert result.merged_entries == 1
    assert result.ignored_entries == 0
    assert result.new_peers == ()
    assert [peer.node_id for peer in result.updated_peers] == ["node-2"]


def test_remove_peer_returns_typed_result() -> None:
    """Assert that removal uses a typed outcome and updates the snapshot."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    result = table.remove_peer("node-2")

    assert result.peer_id == "node-2"
    assert result.changed is True
    assert result.should_gossip is True
    assert result.reason == "removed"
    assert table.snapshot() == ()


def test_concurrent_updates_to_same_peer_preserve_single_entry() -> None:
    """Assert repeated concurrent updates to one peer never create duplicates."""
    table = PeerTable(self_node_id="node-1")
    inserted_results = 0
    changed_results = 0
    outcome_lock = threading.Lock()
    barrier = threading.Barrier(9)

    def worker() -> None:
        nonlocal inserted_results, changed_results
        barrier.wait()
        local_inserted_results = 0
        local_changed_results = 0
        for _ in range(100):
            result = table.upsert_peer(
                node_id="node-2",
                host="127.0.0.1",
                port=9001,
            )
            local_inserted_results += int(result.inserted)
            local_changed_results += int(result.changed)
        with outcome_lock:
            inserted_results += local_inserted_results
            changed_results += local_changed_results

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()

    barrier.wait()

    for thread in threads:
        thread.join()

    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"
    assert inserted_results == 1
    assert changed_results == 1


def test_concurrent_merge_and_heartbeat_leave_peer_alive() -> None:
    """Assert merge and heartbeat interleavings keep one consistent peer record."""
    table = PeerTable(self_node_id="node-1")
    inserted = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    assert inserted.peer is not None
    table.mark_suspected("node-2", phi=5.0)
    barrier = threading.Barrier(3)
    latest_heartbeat = inserted.peer.last_heartbeat

    def merge_worker() -> None:
        barrier.wait()
        for index in range(50):
            table.merge_membership_view(
                [Peer.new("node-2", f"10.0.0.{index % 3 + 2}", 9001 + (index % 2))]
            )

    def heartbeat_worker() -> None:
        nonlocal latest_heartbeat
        barrier.wait()
        for step in range(50):
            latest_heartbeat += 1.0
            table.mark_alive("node-2", heartbeat_at=latest_heartbeat)

    merge_thread = threading.Thread(target=merge_worker)
    heartbeat_thread = threading.Thread(target=heartbeat_worker)
    merge_thread.start()
    heartbeat_thread.start()
    barrier.wait()
    merge_thread.join()
    heartbeat_thread.join()

    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"
    assert peers[0].status is NodeStatus.ALIVE
    assert peers[0].last_heartbeat == latest_heartbeat
