"""Validate full-sync protocol handlers and delta fallback behavior."""

from __future__ import annotations

from queue import Queue
from typing import cast

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import (
    build_delta_unavailable,
    build_full_sync_request,
    build_full_sync_response,
    build_get_delta,
)
from runtime.state_sync_handlers import (
    make_delta_unavailable_handler,
    make_full_sync_request_handler,
    make_full_sync_response_handler,
    make_get_delta_handler,
)
from protocol.message_types import MessageType
from protocol.messages import Message, PeerDescriptor
from state.node_state_worker import NodeStateWorker
from utils.typing import ReplicationDeltaBatch, SensorEventSource


class DummyLog:
    """Provide the minimal logger interface required by state-worker tests."""

    def debug(self, *args: object, **kwargs: object) -> None:
        pass

    def info(self, *args: object, **kwargs: object) -> None:
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        pass

    def critical(self, *args: object, **kwargs: object) -> None:
        pass


def _event_queue() -> SensorEventSource:
    return cast(SensorEventSource, Queue())


def make_worker(node_id: str = "node-a") -> NodeStateWorker:
    """Create a state worker backed by a fresh in-memory queue."""
    return NodeStateWorker(node_id=node_id, event_queue=_event_queue(), log=DummyLog())


def test_full_sync_request_handler_replies_with_state_and_membership() -> None:
    """Assert FULL_SYNC_REQUEST triggers a FULL_SYNC_RESPONSE with both payload sections."""
    state_worker = make_worker("node-a")
    state_worker.merge_update("s1", 10, 1000, "node-a")

    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_full_sync_request_handler(
        state_worker=state_worker,
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    handler(build_full_sync_request(sender_id="node-b", requester_id="node-b"))

    assert len(sent) == 1
    target, response = sent[0]
    assert target == "node-b"
    assert response.msg_type is MessageType.FULL_SYNC_RESPONSE
    assert response.payload.state["node-a"]["node-a:s1"]["value"] == 10
    assert any(peer.node_id == "node-b" for peer in response.payload.membership)


def test_full_sync_request_handler_defaults_requester_to_sender_when_missing_or_empty() -> None:
    """Assert missing/empty requester_id falls back to transport sender id."""
    state_worker = make_worker("node-a")
    peer_table = PeerTable(self_node_id="node-a")
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_full_sync_request_handler(
        state_worker=state_worker,
        peer_table=peer_table,
        send=send,
        self_node_id="node-a",
    )

    handler(build_full_sync_request(sender_id="node-b", requester_id=None))
    mutated = build_full_sync_request(sender_id="node-c", requester_id=None)
    object.__setattr__(mutated.payload, "requester_id", "")
    handler(mutated)

    assert len(sent) == 2
    assert sent[0][0] == "node-b"
    assert sent[0][1].msg_type is MessageType.FULL_SYNC_RESPONSE
    assert sent[1][0] == "node-c"
    assert sent[1][1].msg_type is MessageType.FULL_SYNC_RESPONSE


def test_full_sync_response_handler_merges_state_and_membership() -> None:
    """Assert FULL_SYNC_RESPONSE applies LWW state and peer-table membership updates."""
    state_worker = make_worker("node-a")
    state_worker.merge_update("s1", 1, 1000, "node-a")

    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)

    discovered: list[str] = []

    def on_peer_discovered(peer: Peer) -> None:
        discovered.append(peer.node_id)

    handler = make_full_sync_response_handler(
        state_worker=state_worker,
        peer_table=peer_table,
        self_node_id="node-a",
        on_peer_discovered=on_peer_discovered,
    )

    response = build_full_sync_response(
        sender_id="node-b",
        state={
            "node-b": {
                "node-b:s1": {
                    "value": 99,
                    "ts_ms": 2000,
                    "origin": "node-b",
                    "meta": {"unit": "C", "period_ms": 1000},
                }
            }
        },
        membership=(
            PeerDescriptor(node_id="node-b", host="10.0.0.2", port=9002),
            PeerDescriptor(node_id="node-c", host="10.0.0.3", port=9003),
        ),
    )
    handler(response)

    state = state_worker.get_state_snapshot()["node-a"]
    assert state["node-b:s1"]["value"] == 99
    assert state["node-b:s1"]["origin"] == "node-b"
    assert peer_table.get_peer("node-c") is not None
    assert "node-c" in discovered


def test_delta_unavailable_triggers_full_sync_request() -> None:
    """Assert DELTA_UNAVAILABLE causes an immediate FULL_SYNC_REQUEST fallback."""
    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_delta_unavailable_handler(send=send, self_node_id="node-a")
    handler(build_delta_unavailable(sender_id="node-b", reason="missing history"))

    assert len(sent) == 1
    target, req = sent[0]
    assert target == "node-b"
    assert req.msg_type is MessageType.FULL_SYNC_REQUEST
    assert req.payload.requester_id == "node-a"


def test_get_delta_handler_streams_sensor_updates() -> None:
    """Assert GET_DELTA replies with ordered SENSOR_UPDATE messages."""
    state_worker = make_worker("node-a")
    state_worker.merge_update("s1", 10, 1000, "node-a")
    state_worker.merge_update("s2", 20, 1001, "node-a")

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_get_delta_handler(
        state_worker=state_worker,
        send=send,
        self_node_id="node-a",
    )
    handler(build_get_delta(sender_id="node-b", since_ts_ms=1000))

    assert len(sent) == 1
    target, msg = sent[0]
    assert target == "node-b"
    assert msg.msg_type is MessageType.SENSOR_UPDATE
    assert msg.payload.sensor_id == "s2"
    assert msg.payload.ts_ms == 1001


def test_get_delta_handler_returns_delta_unavailable_for_stale_cursor() -> None:
    """Assert GET_DELTA stale cursors trigger DELTA_UNAVAILABLE fallback."""
    state_worker = NodeStateWorker(
        node_id="node-a",
        event_queue=_event_queue(),
        log=DummyLog(),
        replication_delta_maxlen=2,
    )
    state_worker.merge_update("s1", 10, 1000, "node-a")
    state_worker.merge_update("s2", 20, 1001, "node-a")
    state_worker.merge_update("s3", 30, 1002, "node-a")

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_get_delta_handler(
        state_worker=state_worker,
        send=send,
        self_node_id="node-a",
    )
    handler(build_get_delta(sender_id="node-b", since_ts_ms=999))

    assert len(sent) == 1
    target, msg = sent[0]
    assert target == "node-b"
    assert msg.msg_type is MessageType.DELTA_UNAVAILABLE


def test_get_delta_handler_skips_malformed_entries_and_sends_only_valid_updates() -> None:
    """Assert GET_DELTA ignores malformed entries and serves only valid deltas."""

    class FakeStateWorker:
        def get_replication_deltas_since(
            self,
            *,
            since_ts_ms: int,
        ) -> ReplicationDeltaBatch | None:
            assert since_ts_ms == 1000
            return cast(
                ReplicationDeltaBatch,
                (
                {
                    "sensor_id": "s-good",
                    "value": 42,
                    "ts_ms": 1001,
                    "origin": "node-a",
                    "meta": {"unit": "C", "period_ms": 1000},
                },
                {
                    "sensor_id": "",
                    "value": 1,
                    "ts_ms": 1002,
                    "origin": "node-a",
                    "meta": {},
                },
                {
                    "sensor_id": "s-bad-origin",
                    "value": 2,
                    "ts_ms": 1003,
                    "origin": "",
                    "meta": {},
                },
                {
                    "sensor_id": "s-bad-ts",
                    "value": 3,
                    "ts_ms": "1004",
                    "origin": "node-a",
                    "meta": {},
                },
                ),
            )

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    handler = make_get_delta_handler(
        state_worker=FakeStateWorker(),
        send=send,
        self_node_id="node-a",
    )
    handler(build_get_delta(sender_id="node-b", since_ts_ms=1000))

    assert len(sent) == 1
    target, msg = sent[0]
    assert target == "node-b"
    assert msg.msg_type is MessageType.SENSOR_UPDATE
    assert msg.payload.sensor_id == "s-good"
    assert msg.payload.value == 42
    assert msg.payload.ts_ms == 1001
    assert msg.payload.origin == "node-a"
    assert msg.payload.meta.unit == "C"
    assert msg.payload.meta.period_ms == 1000


def test_full_sync_response_merges_membership_even_when_state_is_rejected() -> None:
    """Assert membership merge still applies when strict state merge rejects payload."""
    state_worker = make_worker("node-a")
    state_worker.merge_update("s1", 10, 1000, "node-a")
    before = state_worker.get_state_snapshot()["node-a"].copy()

    peer_table = PeerTable(self_node_id="node-a")
    handler = make_full_sync_response_handler(
        state_worker=state_worker,
        peer_table=peer_table,
        self_node_id="node-a",
    )

    response = build_full_sync_response(
        sender_id="node-b",
        state={"node-b": {}},
        membership=(PeerDescriptor(node_id="node-c", host="10.0.0.3", port=9003),),
    )
    handler(response)

    assert peer_table.get_peer("node-c") is not None
    assert state_worker.get_state_snapshot()["node-a"] == before
