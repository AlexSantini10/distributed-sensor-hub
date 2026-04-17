"""Track short-lived pull windows to classify inbound SENSOR_UPDATE messages."""

from __future__ import annotations

import threading
import time


class PullResponseTracker:
    """Track pending GET_DELTA requests and classify follow-up updates."""

    def __init__(self, *, default_window_s: float = 1.5) -> None:
        if default_window_s <= 0:
            raise ValueError("default_window_s must be > 0")
        self._default_window_s = default_window_s
        self._lock = threading.Lock()
        self._pending_until_by_peer: dict[str, float] = {}

    def mark_pull_requested(self, peer_id: str, *, window_s: float | None = None) -> None:
        """Mark that we requested deltas from ``peer_id`` just now."""
        if not isinstance(peer_id, str) or peer_id == "":
            return
        ttl = self._default_window_s if window_s is None else window_s
        if ttl <= 0:
            return
        deadline = time.monotonic() + ttl
        with self._lock:
            self._pending_until_by_peer[peer_id] = deadline

    def classify_sender(self, sender_id: str) -> str:
        """Classify an inbound sender as ``pull`` or ``push``."""
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
