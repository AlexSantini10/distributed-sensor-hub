"""Validate DEMO logging excludes heartbeat protocol noise."""

import threading
import logging
from pathlib import Path
import uuid

from membership.peer_table import PeerTable
from runtime.heartbeat import HeartbeatSender
from utils.config import LogLevel
from utils.logging import get_logger, setup_logging


def test_demo_mode_does_not_emit_ping_pong_lines() -> None:
    """Assert heartbeat rounds do not emit ``[DEMO] PING/PONG`` lines."""
    tmp_dir = Path(".codex-tmp") / "test-logging"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_dir / f"test-demo-heartbeat-noise-{uuid.uuid4().hex}.log"

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    setup_logging("node-a", LogLevel.DEMO, str(log_file))
    log = get_logger("runtime.heartbeat", "node-a")

    peer_table = PeerTable(self_node_id="node-a")
    peer_table.upsert_peer(node_id="node-b", host="10.0.0.2", port=9002)
    sent: list[tuple[str, object]] = []
    lock = threading.Lock()

    def send(peer_id: str, msg: object) -> None:
        with lock:
            sent.append((peer_id, msg))

    sender = HeartbeatSender(
        self_node_id="node-a",
        peer_table=peer_table,
        send=send,
        interval_ms=100,
        log=log,
    )
    try:
        sender._send_heartbeat_round()
        content = log_file.read_text(encoding="utf-8")
        assert "[DEMO] PING" not in content
        assert "[DEMO] PONG" not in content
    finally:
        for handler in list(root.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
