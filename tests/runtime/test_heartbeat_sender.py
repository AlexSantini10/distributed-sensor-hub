"""Validate background heartbeat sender behavior."""

from __future__ import annotations

import threading
import time
import logging

from membership.peer_table import PeerTable
from protocol.message import Message
from protocol.message_types import MessageType
from runtime.heartbeat import HeartbeatSender
from topology.state import TopologyStateStore
from utils.logging import get_logger


class DummyLog:
    """Provide the minimal logger interface used by the heartbeat sender."""

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

    def demo(self, *args: object, **kwargs: object) -> None:
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


def test_heartbeat_sender_logs_phi_transition(caplog, monkeypatch) -> None:
    """Assert phi-driven membership transitions are logged with context."""
    peer_table = PeerTable(
        self_node_id="node-a",
        phi_threshold_suspect=0.5,
        phi_threshold_dead=2.0,
        phi_initial_interval_s=1.0,
    )
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    base = time.time() + 1000.0
    peer_table.record_heartbeat("node-b", heartbeat_at=base, arrived_at_monotonic_s=10.0)
    peer_table.record_heartbeat("node-b", heartbeat_at=base + 1.0, arrived_at_monotonic_s=11.0)

    def send(_peer_id: str, _msg: Message) -> None:
        pass

    sender = HeartbeatSender(
        self_node_id="node-a",
        peer_table=peer_table,
        send=send,
        interval_ms=50,
        log=get_logger("runtime.heartbeat", "node-a"),
    )
    monkeypatch.setattr("runtime.heartbeat.time.monotonic", lambda: 12.2)
    monkeypatch.setattr("runtime.heartbeat.time.time", lambda: base + 2.2)
    with caplog.at_level(logging.INFO, logger="runtime.heartbeat"):
        sender._send_heartbeat_round()

    assert "Membership transition from phi detector" in caplog.text
    assert "peer=node-b" in caplog.text
    assert "from=alive to=suspected" in caplog.text


def test_heartbeat_sender_pings_all_and_only_connected_peers() -> None:
    """Assert heartbeat probes target exactly the currently connected peer set."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    peer_table.upsert_peer(node_id="node-c", host="10.0.0.3", port=9003)
    peer_table.upsert_peer(node_id="node-d", host="10.0.0.4", port=9004)

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    sender = HeartbeatSender(
        self_node_id="node-a",
        peer_table=peer_table,
        send=send,
        interval_ms=100,
        log=DummyLog(),
        connected_peer_ids_provider=lambda: ("node-b", "node-d"),
    )
    sender._send_heartbeat_round()

    ping_targets = {
        peer_id
        for peer_id, msg in sent
        if msg.msg_type is MessageType.PING
    }
    assert ping_targets == {"node-b", "node-d"}


def test_heartbeat_sender_gossip_includes_topology_snapshot() -> None:
    """Assert heartbeat gossip includes topology entries when store is configured."""
    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)

    topology_state = TopologyStateStore(self_node_id="node-a")
    topology_state.set_local_neighbors(("node-b",))

    sent: list[tuple[str, Message]] = []

    def send(peer_id: str, msg: Message) -> None:
        sent.append((peer_id, msg))

    sender = HeartbeatSender(
        self_node_id="node-a",
        peer_table=peer_table,
        send=send,
        interval_ms=100,
        log=DummyLog(),
        topology_state=topology_state,
    )
    sender._send_heartbeat_round()

    gossip_messages = [msg for _, msg in sent if msg.msg_type is MessageType.GOSSIP_STATE]
    assert len(gossip_messages) >= 1
    state = gossip_messages[0].payload.state
    assert "topology" in state
    assert isinstance(state["topology"], dict)
    entries = state["topology"].get("entries", [])
    assert isinstance(entries, list)
    assert len(entries) == 1
    assert entries[0]["node_id"] == "node-a"
    assert entries[0]["direct_neighbors"] == ["node-b"]
    assert isinstance(entries[0]["updated_at_ms"], int)
