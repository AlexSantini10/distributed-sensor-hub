from protocol.message import Message
from protocol.message_types import MessageType

from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.handlers import make_membership_handlers


class FakeSender:
    """
    Fake sender capturing outgoing messages.
    """

    def __init__(self):
        self.sent = []

    def send(self, peer_id: str, msg: Message) -> None:
        self.sent.append((peer_id, msg))


def test_join_request_adds_peer_and_replies_with_peer_list():
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    join_msg = Message(
        msg_type=MessageType.JOIN_REQUEST,
        sender_id="transport-peer",
        payload={
            "node_id": "node-2",
            "host": "127.0.0.1",
            "port": 9001,
        },
    )

    handle_join(join_msg)

    # Peer added
    peer = table.get_peer("node-2")
    assert peer is not None
    assert peer.host == "127.0.0.1"
    assert peer.port == 9001

    # Reply sent
    assert len(sender.sent) == 1
    sent_peer_id, reply = sender.sent[0]

    assert sent_peer_id == "transport-peer"
    assert reply.msg_type == MessageType.PEER_LIST

    peers = reply.payload["peers"]
    assert isinstance(peers, list)
    assert len(peers) == 1
    assert peers[0]["node_id"] == "node-2"


def test_join_request_idempotent():
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    msg = Message(
        msg_type=MessageType.JOIN_REQUEST,
        sender_id="peer-x",
        payload={
            "node_id": "node-2",
            "host": "127.0.0.1",
            "port": 9001,
        },
    )

    handle_join(msg)
    handle_join(msg)

    peers = table.list_peers()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"

    # Still replies (protocol is idempotent but responsive)
    assert len(sender.sent) == 2


def test_join_request_self_ignored():
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    msg = Message(
        msg_type=MessageType.JOIN_REQUEST,
        sender_id="loopback",
        payload={
            "node_id": "node-1",
            "host": "127.0.0.1",
            "port": 9000,
        },
    )

    handle_join(msg)

    assert table.list_peers() == []
    assert sender.sent == []


def test_peer_list_integrates_new_peers_only():
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    # Existing peer
    table.add_peer(Peer.new("node-2", "127.0.0.1", 9001))

    peer_list_msg = Message(
        msg_type=MessageType.PEER_LIST,
        sender_id="peer-x",
        payload={
            "peers": [
                {"node_id": "node-2", "host": "127.0.0.1", "port": 9001},
                {"node_id": "node-3", "host": "127.0.0.1", "port": 9002},
            ]
        },
    )

    handle_peer_list(peer_list_msg)

    peers = table.list_peers()
    ids = {p.node_id for p in peers}

    assert ids == {"node-2", "node-3"}
