"""Validate background heartbeat sender behavior."""

from __future__ import annotations

import threading
import time

from membership.peer_table import PeerTable
from protocol.message import Message
from protocol.message_types import MessageType
from runtime.heartbeat import HeartbeatSender


class DummyLog:
    """Provide the minimal logger interface used by the heartbeat sender."""

    def debug(self, *args: object, **kwargs: object) -> None:
        pass


def test_heartbeat_sender_runs_in_background_and_emits_pings() -> None:
    """Assert heartbeat sender emits PING and GOSSIP_STATE without blocking."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    peer_table.upsert_peer(node_id="node-c", host="10.0.0.3", port=9003)

    sent: list[tuple[str, Message]] = []
    lock = threading.Lock()
    sent_event = threading.Event()

    def send(peer_id: str, msg: Message) -> None:
        with lock:
            sent.append((peer_id, msg))
        sent_event.set()

    sender = HeartbeatSender(
        self_node_id="node-a",
        peer_table=peer_table,
        send=send,
        interval_ms=50,
        log=DummyLog(),
    )

    start = time.monotonic()
    sender.start()
    startup_elapsed = time.monotonic() - start
    delivered = sent_event.wait(timeout=0.5)
    sender.stop()

    assert startup_elapsed < 0.1
    assert delivered is True
    assert sent
    assert any(msg.msg_type is MessageType.PING for _, msg in sent)
    assert any(msg.msg_type is MessageType.GOSSIP_STATE for _, msg in sent)
