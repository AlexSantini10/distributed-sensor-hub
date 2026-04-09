"""Validate heartbeat protocol handlers."""

from __future__ import annotations

from fd.heartbeat import HeartbeatMonitor
from membership.peer_table import PeerTable
from protocol.factory import build_ping, build_pong
from protocol.handlers import make_heartbeat_handlers
from protocol.message import Message
from protocol.message_types import MessageType


def test_ping_handler_marks_alive_and_replies_with_pong() -> None:
    """Assert incoming PING updates liveness and returns a PONG response."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    monitor = HeartbeatMonitor()
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
        heartbeat_monitor=monitor,
    )

    before = peer_table.get_peer("node-b")
    assert before is not None
    ping_handler(build_ping(sender_id="node-b", ping_timestamp_ms=111))
    after = peer_table.get_peer("node-b")
    assert after is not None

    assert after.last_heartbeat >= before.last_heartbeat
    assert len(sent) == 1
    target, response = sent[0]
    assert target == "node-b"
    assert response.msg_type is MessageType.PONG
    assert response.payload.timestamp_ms is not None
    assert monitor.get_intervals("node-b") == ()


def test_pong_handler_records_inter_arrival_interval() -> None:
    """Assert repeated heartbeat arrivals produce inter-arrival samples."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    monitor = HeartbeatMonitor()

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    ping_handler, pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
        heartbeat_monitor=monitor,
    )

    ping_handler(build_ping(sender_id="node-b", ping_timestamp_ms=111))
    pong_handler(build_pong(sender_id="node-b", pong_timestamp_ms=222))

    intervals = monitor.get_intervals("node-b")
    assert len(intervals) == 1
    assert intervals[0] >= 0.0


def test_ping_handler_ignores_self_ping() -> None:
    """Assert incoming self PING is ignored and does not send a PONG."""
    peer_table = PeerTable(self_node_id="node-a")
    monitor = HeartbeatMonitor()
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    ping_handler, _pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
        heartbeat_monitor=monitor,
    )

    ping_handler(build_ping(sender_id="node-a", ping_timestamp_ms=111))

    assert sent == []
    assert monitor.get_intervals("node-a") == ()


def test_pong_handler_ignores_self_pong() -> None:
    """Assert incoming self PONG is ignored and does not update intervals."""
    peer_table = PeerTable(self_node_id="node-a")
    monitor = HeartbeatMonitor()

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    _ping_handler, pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
        heartbeat_monitor=monitor,
    )

    pong_handler(build_pong(sender_id="node-a", pong_timestamp_ms=222))

    assert monitor.get_intervals("node-a") == ()
