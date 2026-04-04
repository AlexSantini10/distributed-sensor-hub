"""Validate thread-safe peer-table membership contracts."""

import threading
import time

from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.results import (
    PeerStatusOutcome,
    RemovePeerOutcome,
    UpsertPeerOutcome,
)
from membership.status import NodeStatus


def test_upsert_peer_success() -> None:
    """Assert that inserting a new remote peer succeeds with a typed outcome."""
    table = PeerTable(self_node_id="node-1")

    result = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    assert result.outcome is UpsertPeerOutcome.INSERTED
    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "127.0.0.1"
    assert stored.port == 9001


def test_upsert_peer_idempotent() -> None:
    """Assert that inserting the same endpoint twice preserves one entry."""
    table = PeerTable(self_node_id="node-1")

    first = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    second = table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    assert first.outcome is UpsertPeerOutcome.INSERTED
    assert second.outcome is UpsertPeerOutcome.UNCHANGED
    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"


def test_upsert_self_peer_ignored() -> None:
    """Assert that a node never stores itself in the peer table."""
    table = PeerTable(self_node_id="node-1")

    result = table.upsert_peer(node_id="node-1", host="127.0.0.1", port=9000)

    assert result.outcome is UpsertPeerOutcome.IGNORED_SELF
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

    assert result.outcome is PeerStatusOutcome.UPDATED
    updated = table.get_peer("node-2")
    assert updated is not None
    assert updated.last_heartbeat == new_ts
    assert updated.status is NodeStatus.ALIVE
    assert updated.phi == 0.0


def test_mark_alive_unknown_peer_noop() -> None:
    """Assert that heartbeat updates do not create unknown peers."""
    table = PeerTable(self_node_id="node-1")

    result = table.mark_alive("node-unknown", heartbeat_at=time.time())

    assert result.outcome is PeerStatusOutcome.NOT_FOUND
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
    assert [p.node_id for p in merge.added] == ["node-3"]
    assert merge.updated == ()
    assert merge.unchanged == ("node-2",)
    assert merge.ignored_self == ("node-1",)


def test_merge_membership_view_preserves_liveness_state() -> None:
    """Assert that endpoint merges do not reset suspicion metadata."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    table.mark_suspected("node-2", phi=12.0)

    table.merge_membership_view([Peer.new("node-2", "10.0.0.2", 9002)])

    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "10.0.0.2"
    assert stored.port == 9002
    assert stored.status is NodeStatus.SUSPECTED
    assert stored.phi == 12.0


def test_remove_peer_returns_typed_result() -> None:
    """Assert that removal uses a typed outcome and updates the snapshot."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    result = table.remove_peer("node-2")

    assert result.outcome is RemovePeerOutcome.REMOVED
    assert table.snapshot() == ()


def test_concurrent_updates_to_same_peer_preserve_single_entry() -> None:
    """Assert repeated concurrent updates to one peer never create duplicates."""
    table = PeerTable(self_node_id="node-1")
    outcomes: list[UpsertPeerOutcome] = []
    outcome_lock = threading.Lock()
    barrier = threading.Barrier(9)

    def worker() -> None:
        barrier.wait()
        local_outcomes: list[UpsertPeerOutcome] = []
        for _ in range(100):
            result = table.upsert_peer(
                node_id="node-2",
                host="127.0.0.1",
                port=9001,
            )
            local_outcomes.append(result.outcome)
        with outcome_lock:
            outcomes.extend(local_outcomes)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()

    barrier.wait()

    for thread in threads:
        thread.join()

    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"
    assert outcomes.count(UpsertPeerOutcome.INSERTED) == 1
    assert set(outcomes).issubset({UpsertPeerOutcome.INSERTED, UpsertPeerOutcome.UNCHANGED})


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
