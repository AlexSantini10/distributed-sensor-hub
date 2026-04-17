"""Run periodic heartbeat probes against known peers.

Responsibilities:
    - Emit ``PING`` messages to all known peers at a configured interval.
    - Keep heartbeat sending off the main node thread.
    - Stop promptly during node shutdown.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from gossip.publisher import publish_membership_gossip
from membership.peer import Peer
from membership.peer_table import PeerTable
from membership.results import FailureDetectionUpdateResult
from protocol.factory import build_ping
from protocol.message import Message
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
        connected_peer_ids_provider: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        """Initialize a background heartbeat sender."""
        self._self_node_id = self_node_id
        self._peer_table = peer_table
        self._send = send
        self._interval_s = max(0.001, interval_ms / 1000.0)
        self._log = log
        self._stop_event = threading.Event()
        self._connected_peer_ids_provider = connected_peer_ids_provider
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
        """Evaluate phi, publish gossip, then send one PING per peer."""
        fd_updates = self._evaluate_failure_detector()
        self._log_membership_transitions(fd_updates)

        peers = self._peer_table.snapshot()
        connected_peers = self._connected_peers_from_snapshot(peers)
        self._publish_membership_gossip(peers)
        self._send_ping_to_peers(connected_peers)

    def _evaluate_failure_detector(self) -> tuple[FailureDetectionUpdateResult, ...]:
        """Apply phi-accrual evaluation to the current membership view."""
        return self._peer_table.evaluate_failure_detector(
            observed_at_wall_s=time.time(),
            observed_at_monotonic_s=time.monotonic(),
        )

    def _log_membership_transitions(
        self,
        fd_updates: tuple[FailureDetectionUpdateResult, ...],
    ) -> None:
        """Log status changes produced by the failure detector."""
        for update in fd_updates:
            if update.status.changed and update.peer is not None:
                self._log.info(
                    "Membership transition from phi detector: "
                    f"peer={update.peer_id} "
                    f"from={update.status.previous_status} to={update.status.new_status} "
                    f"phi={update.peer.phi:.3f} "
                    f"event_ts_ms={update.peer.status_ts_ms}"
                )

    def _publish_membership_gossip(self, peers: tuple[Peer, ...]) -> None:
        """Publish the current membership view before sending direct probes."""
        publish_membership_gossip(
            self_node_id=self._self_node_id,
            peer_table=self._peer_table,
            peers=peers,
            send=self._send,
            log=self._log,
        )

    def _build_ping(self) -> Message:
        """Build a timestamped heartbeat probe."""
        return build_ping(
            sender_id=self._self_node_id,
            ping_timestamp_ms=int(time.time() * 1000),
        )

    def _send_ping_to_peers(self, peers: tuple[Peer, ...]) -> None:
        """Send one heartbeat probe to each connected peer."""
        ping = self._build_ping()
        for peer in peers:
            try:
                self._send(peer.node_id, ping)
            except Exception:
                self._log.debug(
                    f"Heartbeat PING failed to {peer.node_id} {peer.host}:{peer.port}",
                    exc_info=True,
                )

    def _connected_peers_from_snapshot(self, peers: tuple[Peer, ...]) -> tuple[Peer, ...]:
        """Return peers that are currently registered in outbound transport."""
        if self._connected_peer_ids_provider is None:
            return peers
        connected_ids = set(self._connected_peer_ids_provider())
        if not connected_ids:
            return ()
        return tuple(peer for peer in peers if peer.node_id in connected_ids)
