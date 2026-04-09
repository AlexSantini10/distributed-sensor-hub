"""Run periodic heartbeat probes against known peers.

Responsibilities:
    - Emit ``PING`` messages to all known peers at a configured interval.
    - Keep heartbeat sending off the main node thread.
    - Stop promptly during node shutdown.
"""

from __future__ import annotations

import threading
import time

from membership.peer_table import PeerTable
from protocol.factory import build_gossip_state, build_ping
from utils.typing import LoggerLike, SenderLike


class HeartbeatSender:
    """Send periodic liveness pings to every peer in the membership table."""

    def __init__(
        self,
        *,
        self_node_id: str,
        peer_table: PeerTable,
        send: SenderLike,
        interval_ms: int,
        log: LoggerLike,
    ) -> None:
        """Initialize a background heartbeat sender."""
        self._self_node_id = self_node_id
        self._peer_table = peer_table
        self._send = send
        self._interval_s = max(0.001, interval_ms / 1000.0)
        self._log = log
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="heartbeat-sender",
            daemon=True,
        )
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start periodic heartbeat emission."""
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            self._thread.start()

    def stop(self) -> None:
        """Stop heartbeat emission and wait for worker exit."""
        with self._lock:
            if not self._started:
                return
            self._started = False
            self._stop_event.set()
            thread = self._thread
        if thread.is_alive():
            thread.join(timeout=5.0)

    def _run(self) -> None:
        """Send one heartbeat round per interval until stopped."""
        while not self._stop_event.is_set():
            self._send_heartbeat_round()
            self._stop_event.wait(self._interval_s)

    def _send_heartbeat_round(self) -> None:
        """Evaluate phi, gossip membership state, then send one PING per peer."""
        fd_updates = self._peer_table.evaluate_failure_detector(
            observed_at_wall_s=time.time(),
            observed_at_monotonic_s=time.monotonic(),
        )
        for update in fd_updates:
            if update.status.changed and update.peer is not None:
                self._log.debug(
                    "Phi transition: "
                    f"peer={update.peer_id} "
                    f"from={update.status.previous_status} to={update.status.new_status} "
                    f"phi={update.peer.phi:.3f} "
                    f"status_ts_ms={update.peer.status_ts_ms}"
                )

        now_ms = int(time.time() * 1000)
        ping = build_ping(
            sender_id=self._self_node_id,
            ping_timestamp_ms=now_ms,
        )
        peers = self._peer_table.snapshot()
        gossip = build_gossip_state(
            sender_id=self._self_node_id,
            state=self._peer_table.build_gossip_state(),
        )

        for peer in peers:
            try:
                self._send(peer.node_id, gossip)
            except Exception:
                self._log.debug(
                    f"GOSSIP_STATE send failed to {peer.node_id} {peer.host}:{peer.port}",
                    exc_info=True,
                )

        for peer in peers:
            try:
                self._send(peer.node_id, ping)
            except Exception:
                self._log.debug(
                    f"Heartbeat PING failed to {peer.node_id} {peer.host}:{peer.port}",
                    exc_info=True,
                )
