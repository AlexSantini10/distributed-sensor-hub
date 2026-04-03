"""Validate membership message handling contracts.

Responsibilities:
    - Assert join requests add peers and return a peer list.
    - Verify idempotent handling and self-join suppression.
    - Confirm peer-list merges add only previously unknown peers.
"""

from protocol.message import Message
from protocol.message_types import MessageType

from membership.handlers import make_membership_handlers
from membership.peer import Peer
from membership.peer_table import PeerTable


class FakeSender:
    """Capture outbound membership messages for assertions.

    Attributes:
        sent (list): Ordered list of ``(peer_id, msg)`` tuples emitted by handlers.
    """

    def __init__(self) -> None:
        """Initialize an empty outbound message capture buffer.

        Returns:
            None: This constructor does not return a value.
        """
        self.sent = []

    def send(self, peer_id: str, msg: Message) -> None:
        """Record one outbound membership message.

        Args:
            peer_id (str): Transport peer identifier selected by the handler.
            msg (Message): Membership message emitted by the handler.

        Returns:
            None: This method appends to the capture buffer.
        """
        self.sent.append((peer_id, msg))


def test_join_request_adds_peer_and_replies_with_peer_list() -> None:
    """Assert that a join request mutates membership and returns the peer list.

    Returns:
        None: This test asserts join-request handling.
    """
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

    peer = table.get_peer("node-2")
    assert peer is not None
    assert peer.host == "127.0.0.1"
    assert peer.port == 9001

    assert len(sender.sent) == 1
    sent_peer_id, reply = sender.sent[0]

    assert sent_peer_id == "transport-peer"
    assert reply.msg_type == MessageType.PEER_LIST

    peers = reply.payload["peers"]
    assert isinstance(peers, list)
    assert len(peers) == 1
    assert peers[0]["node_id"] == "node-2"


def test_join_request_idempotent() -> None:
    """Assert that duplicate join requests do not duplicate peers.

    Returns:
        None: This test asserts idempotent membership updates.
    """
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
    assert len(sender.sent) == 2


def test_join_request_self_ignored() -> None:
    """Assert that a node ignores join requests that advertise itself.

    Returns:
        None: This test asserts self-join suppression.
    """
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


def test_peer_list_integrates_new_peers_only() -> None:
    """Assert that peer-list handling adds only previously unknown peers.

    Returns:
        None: This test asserts peer-list merge semantics.
    """
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

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
