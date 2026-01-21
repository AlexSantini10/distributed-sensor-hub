import time

from membership.peer import Peer
from membership.peer_table import PeerTable


def test_add_peer_success():
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)
    added = table.add_peer(peer)

    assert added is True
    assert table.get_peer("node-2") is peer


def test_add_peer_idempotent():
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)

    assert table.add_peer(peer) is True
    assert table.add_peer(peer) is False

    peers = table.list_peers()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"


def test_add_self_peer_ignored():
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-1", "127.0.0.1", 9000)
    added = table.add_peer(peer)

    assert added is False
    assert table.get_peer("node-1") is None
    assert table.list_peers() == []


def test_update_heartbeat_existing_peer():
    table = PeerTable(self_node_id="node-1")

    peer = Peer.new("node-2", "127.0.0.1", 9001)
    table.add_peer(peer)

    old_ts = peer.last_heartbeat
    new_ts = old_ts + 10.0

    table.update_heartbeat("node-2", new_ts)

    updated = table.get_peer("node-2")
    assert updated is not None
    assert updated.last_heartbeat == new_ts
    assert updated.status == "alive"


def test_update_heartbeat_unknown_peer_noop():
    table = PeerTable(self_node_id="node-1")

    # Should not raise and should not create the peer
    table.update_heartbeat("node-unknown", time.time())

    assert table.get_peer("node-unknown") is None
    assert table.list_peers() == []


def test_list_peers_returns_snapshot():
    table = PeerTable(self_node_id="node-1")

    peer1 = Peer.new("node-2", "127.0.0.1", 9001)
    peer2 = Peer.new("node-3", "127.0.0.1", 9002)

    table.add_peer(peer1)
    snapshot = table.list_peers()

    # Mutate table after snapshot
    table.add_peer(peer2)

    # Snapshot must not change
    assert len(snapshot) == 1
    assert snapshot[0].node_id == "node-2"

    # Table has both peers
    peers = table.list_peers()
    assert {p.node_id for p in peers} == {"node-2", "node-3"}
