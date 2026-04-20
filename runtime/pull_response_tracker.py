"""Track short-lived pull windows to classify inbound ``SENSOR_UPDATE`` messages.

Responsibilities:
    - Mark outbound ``GET_DELTA`` requests as pending pull windows per peer.
    - Classify inbound updates as ``pull`` while a peer window is active.
    - Expire stale windows to keep classification bounded and deterministic.
"""

from __future__ import annotations

import threading
import time


class PullResponseTracker:
    """Track pending ``GET_DELTA`` requests and classify follow-up updates.

    Attributes:
        _default_window_s (float): Default pull classification window in seconds.
        _lock (threading.Lock): Mutex guarding concurrent window updates/lookups.
        _pending_until_by_peer (dict[str, float]): Per-peer monotonic deadlines.
        _last_seq_by_peer (dict[str, int]): Latest pull cursor observed per peer.
    """

    def __init__(self, *, default_window_s: float = 1.5) -> None:
        """Initialize the pull-response classifier.

        Args:
            default_window_s (float): Default TTL applied when no explicit window
                is supplied to ``mark_pull_requested``.

        Returns:
            None: This constructor stores classifier settings only.
        """
        if default_window_s <= 0:
            raise ValueError("default_window_s must be > 0")
        self._default_window_s = default_window_s
        self._lock = threading.Lock()
        self._pending_until_by_peer: dict[str, float] = {}
        self._last_seq_by_peer: dict[str, int] = {}

    def mark_pull_requested(self, peer_id: str, *, window_s: float | None = None) -> None:
        """Mark that we requested deltas from ``peer_id`` just now.

        Args:
            peer_id (str): Peer identifier targeted by ``GET_DELTA``.
            window_s (float | None): Optional TTL override for this peer request.

        Returns:
            None: This method updates in-memory classification windows.
        """
        if not isinstance(peer_id, str) or peer_id == "":
            return
        ttl = self._default_window_s if window_s is None else window_s
        if ttl <= 0:
            return
        deadline = time.monotonic() + ttl
        with self._lock:
            self._pending_until_by_peer[peer_id] = deadline

    def classify_sender(self, sender_id: str) -> str:
        """Classify an inbound sender as ``pull`` or ``push``.

        Args:
            sender_id (str): Transport sender id of the inbound update.

        Returns:
            str: ``"pull"`` when sender has an active pull window, otherwise ``"push"``.
        """
        if not isinstance(sender_id, str) or sender_id == "":
            return "push"
        now = time.monotonic()
        with self._lock:
            expired = [
                peer_id
                for peer_id, deadline in self._pending_until_by_peer.items()
                if deadline <= now
            ]
            for peer_id in expired:
                self._pending_until_by_peer.pop(peer_id, None)

            deadline = self._pending_until_by_peer.get(sender_id)
            if deadline is not None and deadline > now:
                return "pull"

        return "push"

    def observe_replication_seq(self, sender_id: str, source: str, seq: int) -> None:
        """Record a replication sequence observed from an inbound update.

        Args:
            sender_id (str): Transport sender id of the inbound update.
            source (str): Classified source label (``pull`` or ``push``).
            seq (int): Replication sequence carried by the update.

        Returns:
            None: This method updates in-memory pull cursors only.
        """
        if source != "pull":
            return
        if not isinstance(sender_id, str) or sender_id == "":
            return
        if not isinstance(seq, int):
            return
        with self._lock:
            previous = self._last_seq_by_peer.get(sender_id, -1)
            if seq > previous:
                self._last_seq_by_peer[sender_id] = seq

    def get_last_seq_for_peer(self, peer_id: str) -> int:
        """Return the latest pull cursor observed for ``peer_id``.

        Args:
            peer_id (str): Remote peer identifier.

        Returns:
            int: Last observed pull cursor, or ``-1`` when unknown.
        """
        if not isinstance(peer_id, str) or peer_id == "":
            return -1
        with self._lock:
            return self._last_seq_by_peer.get(peer_id, -1)
