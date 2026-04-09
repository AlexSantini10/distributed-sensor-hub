"""Validate heartbeat protocol handlers."""

from __future__ import annotations

import logging

from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.status import NodeStatus
from protocol.handlers import make_heartbeat_handlers
from protocol.message import Message
from protocol.message_types import MessageType
from protocol.factory import build_ping, build_pong


def test_ping_handler_marks_alive_and_replies_with_pong() -> None:
    """Assert incoming PING updates liveness and returns a PONG response."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None
    peer_table.merge_gossip_state(
        [
            Peer(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                liveness=NodeLiveness(
                    last_heartbeat=1.0,
                    phi=0.0,
                    status=NodeStatus.DEAD,
                    status_ts_ms=current.status_ts_ms + 10,
                ),
            )
        ]
    )
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    ping_handler(build_ping(sender_id="node-b", ping_timestamp_ms=111))
    after = peer_table.get_peer("node-b")
    assert after is not None

    assert after.status is NodeStatus.ALIVE
    assert len(sent) == 1
    target, response = sent[0]
    assert target == "node-b"
    assert response.msg_type is MessageType.PONG
    assert response.payload.timestamp_ms is not None


def test_pong_handler_marks_peer_alive() -> None:
    """Assert incoming PONG updates peer status to alive."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None
    peer_table.merge_gossip_state(
        [
            Peer(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                liveness=NodeLiveness(
                    last_heartbeat=1.0,
                    phi=0.0,
                    status=NodeStatus.SUSPECTED,
                    status_ts_ms=current.status_ts_ms + 10,
                ),
            )
        ]
    )

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    _ping_handler, pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    pong_handler(build_pong(sender_id="node-b", pong_timestamp_ms=222))

    peer = peer_table.get_peer("node-b")
    assert peer is not None
    assert peer.status is NodeStatus.ALIVE


def test_ping_handler_ignores_self_ping() -> None:
    """Assert incoming self PING is ignored and does not send a PONG."""
    peer_table = PeerTable(self_node_id="node-a")
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    ping_handler(build_ping(sender_id="node-a", ping_timestamp_ms=111))

    assert sent == []


def test_pong_handler_ignores_self_pong() -> None:
    """Assert incoming self PONG is ignored."""
    peer_table = PeerTable(self_node_id="node-a")

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    _ping_handler, pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    pong_handler(build_pong(sender_id="node-a", pong_timestamp_ms=222))
    assert peer_table.snapshot() == ()


def test_ping_handler_rejects_invalid_payload() -> None:
    """Assert invalid payloads are rejected without side effects."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    ping_handler(build_pong(sender_id="node-b", pong_timestamp_ms=123))
    assert sent == []


def test_ping_handler_logs_transition_back_to_alive(caplog) -> None:
    """Assert heartbeat recovery logs a membership state transition."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None
    peer_table.merge_gossip_state(
        [
            Peer(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                liveness=NodeLiveness(
                    last_heartbeat=1.0,
                    phi=0.0,
                    status=NodeStatus.DEAD,
                    status_ts_ms=current.status_ts_ms + 10,
                ),
            )
        ]
    )

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    ping_handler, _ = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )
    with caplog.at_level(logging.INFO, logger="protocol.handlers"):
        ping_handler(build_ping(sender_id="node-b", ping_timestamp_ms=123))

    assert "Membership transition on heartbeat" in caplog.text
    assert "peer=node-b" in caplog.text
    assert "from=dead to=alive" in caplog.text


def test_ping_from_unknown_peer_still_replies_with_pong_without_mutating_membership() -> None:
    """Assert unknown PING senders still receive PONG but are not auto-inserted."""
    peer_table = PeerTable(self_node_id="node-a")
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _ = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    ping_handler(build_ping(sender_id="node-z", ping_timestamp_ms=999))

    assert peer_table.get_peer("node-z") is None
    assert len(sent) == 1
    target, response = sent[0]
    assert target == "node-z"
    assert response.msg_type is MessageType.PONG


def test_ping_handler_send_failure_is_swallowed_after_liveness_update(caplog) -> None:
    """Assert PONG send failures do not abort heartbeat processing."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    current = peer_table.get_peer("node-b")
    assert current is not None
    peer_table.merge_gossip_state(
        [
            Peer(
                node_id="node-b",
                host="10.0.0.2",
                port=9002,
                liveness=NodeLiveness(
                    last_heartbeat=1.0,
                    phi=0.0,
                    status=NodeStatus.SUSPECTED,
                    status_ts_ms=current.status_ts_ms + 10,
                ),
            )
        ]
    )

    def failing_send(_peer_id: str, _msg: Message) -> None:
        raise RuntimeError("network down")

    ping_handler, _ = make_heartbeat_handlers(
        peer_table=peer_table,
        send=failing_send,
        self_node_id="node-a",
    )
    with caplog.at_level(logging.WARNING, logger="protocol.handlers"):
        ping_handler(build_ping(sender_id="node-b", ping_timestamp_ms=123))

    after = peer_table.get_peer("node-b")
    assert after is not None
    assert after.status is NodeStatus.ALIVE
    assert "Failed to send PONG to node-b" in caplog.text
