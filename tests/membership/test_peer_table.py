"""Validate peer-table membership contracts.

Responsibilities:
    - Assert peer addition, idempotence, and self-peer suppression.
    - Verify heartbeat updates only affect known peers.
    - Confirm peer listings are snapshot copies rather than live views.
"""

import time

from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus


def test_add_peer_success() -> None:
    """Assert that adding a new remote peer succeeds.

    Returns:
        None: This test asserts basic membership insertion.
    """
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)
    added = table.add_peer(peer)

    assert added is True
    assert table.get_peer("node-2") is peer


def test_add_peer_idempotent() -> None:
    """Assert that adding the same peer twice preserves a single entry.

    Returns:
        None: This test asserts idempotent peer insertion.
    """
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)

    assert table.add_peer(peer) is True
    assert table.add_peer(peer) is False

    peers = table.list_peers()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"


def test_add_self_peer_ignored() -> None:
    """Assert that a node never stores itself in the peer table.

    Returns:
        None: This test asserts the self-peer invariant.
    """
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-1", "127.0.0.1", 9000)
    added = table.add_peer(peer)

    assert added is False
    assert table.get_peer("node-1") is None
    assert table.list_peers() == []


def test_update_heartbeat_existing_peer() -> None:
    """Assert that heartbeat updates refresh status for known peers.

    Returns:
        None: This test asserts heartbeat mutation behavior.
    """
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)
    table.add_peer(peer)
    peer.status = NodeStatus.SUSPECTED

    old_ts = peer.last_heartbeat
    new_ts = old_ts + 10.0

    table.update_heartbeat("node-2", new_ts)

    updated = table.get_peer("node-2")
    assert updated is not None
    assert updated.last_heartbeat == new_ts
    assert updated.status is NodeStatus.ALIVE


def test_update_heartbeat_unknown_peer_noop() -> None:
    """Assert that heartbeat updates do not create unknown peers.

    Returns:
        None: This test asserts no-op behavior for unknown peers.
    """
    table = PeerTable(self_node_id="node-1")

    table.update_heartbeat("node-unknown", time.time())

    assert table.get_peer("node-unknown") is None
    assert table.list_peers() == []


def test_list_peers_returns_snapshot() -> None:
    """Assert that listed peers are a point-in-time snapshot.

    Returns:
        None: This test asserts snapshot isolation for peer listings.
    """
    table = PeerTable(self_node_id="node-1")

    peer1 = Peer.new("node-2", "127.0.0.1", 9001)
    peer2 = Peer.new("node-3", "127.0.0.1", 9002)

    table.add_peer(peer1)
    snapshot = table.list_peers()

    table.add_peer(peer2)

    assert len(snapshot) == 1
    assert snapshot[0].node_id == "node-2"

    peers = table.list_peers()
    assert {p.node_id for p in peers} == {"node-2", "node-3"}


def test_new_peer_uses_typed_alive_status() -> None:
    """Assert that new peers start with the enum-backed alive state.

    Returns:
        None: This test asserts enum-based status initialization.
    """
    peer = Peer.new("node-2", "127.0.0.1", 9001)

    assert peer.status is NodeStatus.ALIVE
    assert peer.status.to_wire() == "alive"
