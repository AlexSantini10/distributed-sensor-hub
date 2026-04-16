"""Validate membership handler orchestration contracts."""

import json

import pytest

from membership.peer_table import PeerTable
from protocol.factory import build_join_request, build_peer_list, build_ping
from protocol.message import Message
from protocol.messages import PeerDescriptor, PeerListPayload, ProtocolValidationError
from protocol.handlers.membership import make_membership_handlers


class FakeSender:
    """Capture outbound membership messages for assertions."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, Message]] = []

    def send(self, peer_id: str, msg: Message) -> None:
        self.sent.append((peer_id, msg))


def test_join_request_adds_peer_and_replies_with_peer_list() -> None:
    """Assert that a join request mutates membership and returns the peer list."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    join_msg = build_join_request(
        sender_id="transport-peer",
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
    )

    handle_join(join_msg)

    peer = table.get_peer("node-2")
    assert peer is not None
    assert peer.host == "127.0.0.1"
    assert peer.port == 9001

    assert len(sender.sent) == 1
    sent_peer_id, reply = sender.sent[0]

    assert sent_peer_id == "transport-peer"
    assert reply.msg_type.value == "PEER_LIST"
    assert isinstance(reply.payload, PeerListPayload)
    assert len(reply.payload.peers) == 1
    assert reply.payload.peers[0].node_id == "node-2"


def test_join_request_idempotent() -> None:
    """Assert that duplicate join requests do not duplicate peers."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    msg = build_join_request(
        sender_id="peer-x",
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
    )

    handle_join(msg)
    handle_join(msg)

    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"
    assert len(sender.sent) == 2


def test_duplicate_join_request_notifies_discovery_once() -> None:
    """Assert duplicate join requests do not retrigger discovery side effects."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()
    discovered: list[str] = []

    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
        on_peer_discovered=lambda peer: discovered.append(peer.node_id),
    )

    msg = build_join_request(
        sender_id="peer-x",
        node_id="node-2",
        host="127.0.0.1",
        port=9001,
    )

    handle_join(msg)
    handle_join(msg)

    assert discovered == ["node-2"]


def test_join_request_self_ignored() -> None:
    """Assert that a node ignores join requests that advertise itself."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    msg = build_join_request(
        sender_id="loopback",
        node_id="node-1",
        host="127.0.0.1",
        port=9000,
    )

    handle_join(msg)

    assert table.snapshot() == ()
    assert sender.sent == []


def test_join_handler_rejects_non_join_message_consistently(caplog: pytest.LogCaptureFixture) -> None:
    """Assert the join handler ignores typed messages for another contract."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()
    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    with caplog.at_level("WARNING"):
        handle_join(build_ping(sender_id="peer-x"))

    assert table.snapshot() == ()
    assert sender.sent == []
    assert "Rejected invalid membership message" in caplog.text


def test_peer_list_integrates_new_peers_only() -> None:
    """Assert that peer-list handling adds only previously unknown peers."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()

    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    peer_list_msg = build_peer_list(
        sender_id="peer-x",
        peers=[
            PeerDescriptor(node_id="node-2", host="127.0.0.1", port=9001),
            PeerDescriptor(node_id="node-3", host="127.0.0.1", port=9002),
        ],
    )

    handle_peer_list(peer_list_msg)

    ids = {p.node_id for p in table.snapshot()}
    assert ids == {"node-2", "node-3"}


def test_peer_list_handler_rejects_non_peer_list_message_consistently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Assert the peer-list handler ignores typed messages for another contract."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()
    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    with caplog.at_level("WARNING"):
        handle_peer_list(build_ping(sender_id="peer-x"))

    assert table.snapshot() == ()
    assert sender.sent == []
    assert "Rejected invalid membership message" in caplog.text


def test_peer_list_notifies_only_newly_discovered_peers() -> None:
    """Assert that handler callbacks run only for freshly added peers."""
    table = PeerTable(self_node_id="node-1")
    discovered: list[str] = []
    sender = FakeSender()
    table.upsert_peer(node_id="node-2", host="127.0.0.1", port=9001)

    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
        on_peer_discovered=lambda peer: discovered.append(peer.node_id),
    )

    handle_peer_list(
        build_peer_list(
            sender_id="peer-x",
            peers=[
                PeerDescriptor(node_id="node-2", host="127.0.0.1", port=9001),
                PeerDescriptor(node_id="node-3", host="127.0.0.1", port=9002),
            ],
        )
    )

    assert discovered == ["node-3"]


def test_duplicate_peer_list_is_idempotent() -> None:
    """Assert repeated peer lists do not duplicate peers or notifications."""
    table = PeerTable(self_node_id="node-1")
    discovered: list[str] = []
    sender = FakeSender()

    _handle_join, handle_peer_list = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
        on_peer_discovered=lambda peer: discovered.append(peer.node_id),
    )

    msg = build_peer_list(
        sender_id="peer-x",
        peers=[PeerDescriptor(node_id="node-2", host="127.0.0.1", port=9001)],
    )

    handle_peer_list(msg)
    handle_peer_list(msg)

    peers = table.snapshot()
    assert len(peers) == 1
    assert peers[0].node_id == "node-2"
    assert discovered == ["node-2"]


def test_join_handler_replies_from_snapshot_not_live_peer_object() -> None:
    """Assert that handler replies are built from immutable snapshots."""
    table = PeerTable(self_node_id="node-1")
    sender = FakeSender()
    handle_join, _ = make_membership_handlers(
        peer_table=table,
        send=sender.send,
        self_node_id="node-1",
    )

    handle_join(
        build_join_request(
            sender_id="transport-peer",
            node_id="node-2",
            host="127.0.0.1",
            port=9001,
        )
    )

    snapshot_peer = table.get_peer("node-2")
    assert snapshot_peer is not None
    snapshot_peer.host = "mutated"

    stored = table.get_peer("node-2")
    assert stored is not None
    assert stored.host == "127.0.0.1"


def test_malformed_join_request_is_rejected_at_decode_boundary() -> None:
    """Assert malformed join payloads never reach membership handlers."""
    raw = json.dumps(
        {
            "type": "JOIN_REQUEST",
            "sender_id": "peer-x",
            "timestamp": 1,
            "payload": {
                "node_id": "node-2",
                "host": "127.0.0.1",
            },
        }
    ).encode()

    with pytest.raises(ProtocolValidationError):
        Message.decode(raw)


def test_malformed_peer_list_is_rejected_at_decode_boundary() -> None:
    """Assert malformed peer-list payloads never reach membership handlers."""
    raw = json.dumps(
        {
            "type": "PEER_LIST",
            "sender_id": "peer-x",
            "timestamp": 1,
            "payload": {
                "peers": [
                    {
                        "node_id": "node-2",
                        "host": "127.0.0.1",
                    }
                ]
            },
        }
    ).encode()

    with pytest.raises(ProtocolValidationError):
        Message.decode(raw)
