"""Validate thread-safe peer-table membership contracts."""

import threading
import time

from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus


def _gossip_peer(
    *,
    node_id: str,
    host: str,
    port: int,
    status: NodeStatus,
    status_ts_ms: int,
) -> Peer:
    return Peer(
        node_id=node_id,
        host=host,
        port=port,
        liveness=NodeLiveness(
            last_heartbeat=status_ts_ms / 1000.0,
            phi=0.0,
            status=status,
            status_ts_ms=status_ts_ms,
        ),
    )


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


def test_regular_heartbeat_stream_keeps_peer_alive() -> None:
    """Assert a steady heartbeat stream keeps status alive."""
    table = PeerTable(
        self_node_id="node-1",
        phi_threshold_suspect=2.0,
        phi_threshold_dead=4.0,
        phi_initial_interval_s=1.0,
    )
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    base = time.time() + 1000.0
    table.record_heartbeat("node-2", heartbeat_at=base, arrived_at_monotonic_s=1.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 1.0, arrived_at_monotonic_s=2.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 2.0, arrived_at_monotonic_s=3.0)
    table.evaluate_failure_detector(
        observed_at_wall_s=base + 2.2,
        observed_at_monotonic_s=3.2,
    )

    peer = table.get_peer("node-2")
    assert peer is not None
    assert peer.status is NodeStatus.ALIVE


def test_missing_heartbeats_moves_peer_from_suspected_to_dead() -> None:
    """Assert missing heartbeats first suspect a peer, then mark it dead."""
    table = PeerTable(
        self_node_id="node-1",
        phi_threshold_suspect=0.5,
        phi_threshold_dead=1.2,
        phi_initial_interval_s=1.0,
    )
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    base = time.time() + 1000.0
    table.record_heartbeat("node-2", heartbeat_at=base, arrived_at_monotonic_s=10.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 1.0, arrived_at_monotonic_s=11.0)

    table.evaluate_failure_detector(
        observed_at_wall_s=base + 2.2,
        observed_at_monotonic_s=12.2,
    )
    suspected = table.get_peer("node-2")
    assert suspected is not None
    assert suspected.status is NodeStatus.SUSPECTED

    table.evaluate_failure_detector(
        observed_at_wall_s=base + 4.0,
        observed_at_monotonic_s=14.0,
    )
    dead = table.get_peer("node-2")
    assert dead is not None
    assert dead.status is NodeStatus.DEAD


def test_heartbeat_after_dead_recovers_peer_to_alive() -> None:
    """Assert a new heartbeat clears stale dead suspicion automatically."""
    table = PeerTable(
        self_node_id="node-1",
        phi_threshold_suspect=0.5,
        phi_threshold_dead=1.0,
        phi_initial_interval_s=1.0,
    )
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    base = time.time() + 1000.0
    table.record_heartbeat("node-2", heartbeat_at=base, arrived_at_monotonic_s=10.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 1.0, arrived_at_monotonic_s=11.0)
    table.evaluate_failure_detector(
        observed_at_wall_s=base + 3.5,
        observed_at_monotonic_s=13.5,
    )
    before = table.get_peer("node-2")
    assert before is not None
    assert before.status is NodeStatus.DEAD

    recovery_heartbeat = base + 10.0
    table.record_heartbeat(
        "node-2",
        heartbeat_at=recovery_heartbeat,
        arrived_at_monotonic_s=20.0,
    )
    after = table.get_peer("node-2")
    assert after is not None
    assert after.status is NodeStatus.ALIVE
    assert after.last_heartbeat == recovery_heartbeat
    assert after.status_ts_ms > before.status_ts_ms


def test_remote_stale_suspicion_does_not_override_fresher_local_alive() -> None:
    """Assert LWW merge ignores stale remote suspicion against fresher alive status."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    local_heartbeat = time.time() + 1000.0
    table.record_heartbeat(
        "node-2",
        heartbeat_at=local_heartbeat,
        arrived_at_monotonic_s=5.0,
    )
    local = table.get_peer("node-2")
    assert local is not None
    assert local.status is NodeStatus.ALIVE

    stale_suspected = _gossip_peer(
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
        status=NodeStatus.SUSPECTED,
        status_ts_ms=local.status_ts_ms - 10,
    )
    merge = table.merge_gossip_state([stale_suspected])

    assert merge.changed is False
    current = table.get_peer("node-2")
    assert current is not None
    assert current.status is NodeStatus.ALIVE
    assert current.status_ts_ms == local.status_ts_ms


def test_gossip_merge_is_lww_by_status_timestamp() -> None:
    """Assert newer status timestamps win while older ones are ignored."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    current = table.get_peer("node-2")
    assert current is not None

    dead_newer = _gossip_peer(
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
        status=NodeStatus.DEAD,
        status_ts_ms=current.status_ts_ms + 10,
    )
    table.merge_gossip_state([dead_newer])
    after_dead = table.get_peer("node-2")
    assert after_dead is not None
    assert after_dead.status is NodeStatus.DEAD

    alive_older = _gossip_peer(
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
        status=NodeStatus.ALIVE,
        status_ts_ms=current.status_ts_ms + 9,
    )
    table.merge_gossip_state([alive_older])
    still_dead = table.get_peer("node-2")
    assert still_dead is not None
    assert still_dead.status is NodeStatus.DEAD

    alive_newer = _gossip_peer(
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
        status=NodeStatus.ALIVE,
        status_ts_ms=current.status_ts_ms + 11,
    )
    table.merge_gossip_state([alive_newer])
    recovered = table.get_peer("node-2")
    assert recovered is not None
    assert recovered.status is NodeStatus.ALIVE
    assert recovered.status_ts_ms == current.status_ts_ms + 11


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


def test_merge_membership_view_preserves_liveness_state() -> None:
    """Assert endpoint-only merges do not overwrite current liveness metadata."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    current = table.get_peer("node-2")
    assert current is not None
    table.merge_gossip_state(
        [
            _gossip_peer(
                node_id="node-2",
                host="127.0.0.1",
                port=9001,
                status=NodeStatus.SUSPECTED,
                status_ts_ms=current.status_ts_ms + 10,
            )
        ]
    )

    result = table.merge_membership_view([Peer.new("node-2", "10.0.0.2", 9002)])

    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "10.0.0.2"
    assert stored.port == 9002
    assert stored.status is NodeStatus.SUSPECTED
    assert stored.status_ts_ms == current.status_ts_ms + 10
    assert result.changed is True


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


def test_concurrent_heartbeat_and_gossip_processing_does_not_corrupt_state() -> None:
    """Assert concurrent heartbeat and gossip updates preserve one consistent record."""
    table = PeerTable(self_node_id="node-1")
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    barrier = threading.Barrier(3)

    latest_heartbeat = time.time() + 1000.0
    latest_heartbeat_lock = threading.Lock()

    def gossip_worker() -> None:
        barrier.wait()
        stale = _gossip_peer(
            node_id="node-2",
            host="127.0.0.1",
            port=9001,
            status=NodeStatus.SUSPECTED,
            status_ts_ms=1,
        )
        for _ in range(200):
            table.merge_gossip_state([stale])

    def heartbeat_worker() -> None:
        nonlocal latest_heartbeat
        barrier.wait()
        monotonic_now = 10.0
        for _ in range(200):
            with latest_heartbeat_lock:
                latest_heartbeat += 1.0
                heartbeat_at = latest_heartbeat
            monotonic_now += 1.0
            table.record_heartbeat(
                "node-2",
                heartbeat_at=heartbeat_at,
                arrived_at_monotonic_s=monotonic_now,
            )

    merge_thread = threading.Thread(target=gossip_worker)
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


def test_membership_snapshot_includes_phi_status_and_timestamps() -> None:
    """Assert membership snapshots expose Phi-driven liveness observability fields."""
    table = PeerTable(self_node_id="node-1", phi_max_intervals_per_peer=16)
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    base = time.time() + 1000.0
    table.record_heartbeat("node-2", heartbeat_at=base, arrived_at_monotonic_s=1.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 1.0, arrived_at_monotonic_s=2.0)

    snapshot = table.membership_snapshot()
    assert snapshot["local_node_id"] == "node-1"
    peers = snapshot["peers"]
    assert isinstance(peers, list)
    assert len(peers) == 1
    peer = peers[0]
    assert peer["peer_id"] == "node-2"
    assert peer["status"] == "alive"
    assert isinstance(peer["phi"], float)
    assert peer["last_heartbeat_ts_ms"] == int((base + 1.0) * 1000)
    assert peer["sample_count"] >= 1
    assert peer["sample_window_size"] == 16
    assert isinstance(peer["status_transition_ts_ms"], int)


def test_membership_snapshot_reflects_suspected_dead_then_alive_recovery() -> None:
    """Assert snapshot transitions follow alive -> suspected -> dead -> alive."""
    table = PeerTable(
        self_node_id="node-1",
        phi_threshold_suspect=0.5,
        phi_threshold_dead=2.0,
        phi_initial_interval_s=1.0,
    )
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    base = time.time() + 1000.0
    table.record_heartbeat("node-2", heartbeat_at=base, arrived_at_monotonic_s=10.0)
    table.record_heartbeat("node-2", heartbeat_at=base + 1.0, arrived_at_monotonic_s=11.0)

    table.evaluate_failure_detector(
        observed_at_wall_s=base + 2.2,
        observed_at_monotonic_s=12.2,
    )
    suspected = table.membership_snapshot()["peers"][0]
    assert suspected["status"] == "suspected"

    table.evaluate_failure_detector(
        observed_at_wall_s=base + 6.0,
        observed_at_monotonic_s=16.0,
    )
    dead = table.membership_snapshot()["peers"][0]
    assert dead["status"] == "dead"

    table.record_heartbeat(
        "node-2",
        heartbeat_at=base + 10.0,
        arrived_at_monotonic_s=20.0,
    )
    alive_again = table.membership_snapshot()["peers"][0]
    assert alive_again["status"] == "alive"


def test_membership_snapshot_is_consistent_during_concurrent_updates() -> None:
    """Assert snapshot generation stays safe under concurrent detector and gossip updates."""
    table = PeerTable(
        self_node_id="node-1",
        phi_threshold_suspect=0.5,
        phi_threshold_dead=1.0,
        phi_initial_interval_s=1.0,
    )
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)
    barrier = threading.Barrier(4)
    stop = threading.Event()
    latest_heartbeat = time.time() + 1000.0
    heartbeat_lock = threading.Lock()
    failures: list[Exception] = []

    def heartbeat_worker() -> None:
        nonlocal latest_heartbeat
        try:
            barrier.wait()
            monotonic_now = 10.0
            for _ in range(200):
                with heartbeat_lock:
                    latest_heartbeat += 1.0
                    heartbeat_at = latest_heartbeat
                monotonic_now += 1.0
                table.record_heartbeat(
                    "node-2",
                    heartbeat_at=heartbeat_at,
                    arrived_at_monotonic_s=monotonic_now,
                )
                table.evaluate_failure_detector(
                    observed_at_wall_s=heartbeat_at,
                    observed_at_monotonic_s=monotonic_now,
                )
        except Exception as exc:  # pragma: no cover - defensive test plumbing
            failures.append(exc)
        finally:
            stop.set()

    def gossip_worker() -> None:
        try:
            barrier.wait()
            for i in range(200):
                table.merge_gossip_state(
                    [
                        _gossip_peer(
                            node_id="node-2",
                            host="127.0.0.1",
                            port=9001,
                            status=NodeStatus.SUSPECTED if i % 2 == 0 else NodeStatus.DEAD,
                            status_ts_ms=i + 1,
                        )
                    ]
                )
        except Exception as exc:  # pragma: no cover - defensive test plumbing
            failures.append(exc)

    def snapshot_worker() -> None:
        try:
            barrier.wait()
            while not stop.is_set():
                snap = table.membership_snapshot()
                peers = snap["peers"]
                assert isinstance(peers, list)
                if peers:
                    status = peers[0]["status"]
                    assert status in {"alive", "suspected", "dead"}
                    assert isinstance(peers[0]["phi"], float)
        except Exception as exc:  # pragma: no cover - defensive test plumbing
            failures.append(exc)

    threads = [
        threading.Thread(target=heartbeat_worker),
        threading.Thread(target=gossip_worker),
        threading.Thread(target=snapshot_worker),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert failures == []
