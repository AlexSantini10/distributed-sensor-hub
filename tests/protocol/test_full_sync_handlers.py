"""Validate full-sync protocol handlers and delta fallback behavior."""

from __future__ import annotations

from queue import Queue

from membership.peer import Peer
from membership.peer_table import PeerTable
from protocol.factory import (
    build_delta_unavailable,
    build_full_sync_request,
    build_full_sync_response,
)
from protocol.handlers import (
    make_delta_unavailable_handler,
    make_full_sync_request_handler,
    make_full_sync_response_handler,
)
from protocol.message_types import MessageType
from protocol.messages import Message, PeerDescriptor
from state.node_state_worker import NodeStateWorker


class DummyLog:
    """Provide the minimal logger interface required by state-worker tests."""

    def info(self, *args: object, **kwargs: object) -> None:
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        pass


def make_worker(node_id: str = "node-a") -> NodeStateWorker:
    """Create a state worker backed by a fresh in-memory queue."""
    return NodeStateWorker(node_id=node_id, event_queue=Queue(), log=DummyLog())


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
