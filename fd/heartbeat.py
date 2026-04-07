"""Track heartbeat arrivals for failure-detection inputs.

Responsibilities:
    - Record per-peer heartbeat arrival times under thread-safe access.
    - Compute heartbeat inter-arrival intervals for detector algorithms.
    - Keep bounded interval history to avoid unbounded memory growth.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True, slots=True)
class HeartbeatObservation:
    """Describe one accepted heartbeat arrival."""

    peer_id: str
    arrived_at_s: float
    interval_s: float | None
    sender_timestamp_ms: int | None


class HeartbeatMonitor:
    """Store heartbeat arrival and interval samples per peer."""

    def __init__(self, max_intervals_per_peer: int = 128) -> None:
        """Initialize the heartbeat monitor with bounded sample history."""
        self._lock = threading.Lock()
        self._max_intervals_per_peer = max_intervals_per_peer
        self._last_arrival_s: dict[str, float] = {}
        self._intervals_s: dict[str, list[float]] = {}

    def record_heartbeat(
        self,
        peer_id: str,
        *,
        arrived_at_s: float | None = None,
        sender_timestamp_ms: int | None = None,
    ) -> HeartbeatObservation:
        """Record one heartbeat and compute its inter-arrival interval."""
        arrival = time.monotonic() if arrived_at_s is None else arrived_at_s

        with self._lock:
            previous = self._last_arrival_s.get(peer_id)
            interval: float | None = None
            if previous is not None:
                interval = max(0.0, arrival - previous)
                samples = self._intervals_s.setdefault(peer_id, [])
                samples.append(interval)
                overflow = len(samples) - self._max_intervals_per_peer
                if overflow > 0:
                    del samples[:overflow]
            self._last_arrival_s[peer_id] = arrival

        return HeartbeatObservation(
            peer_id=peer_id,
            arrived_at_s=arrival,
            interval_s=interval,
            sender_timestamp_ms=sender_timestamp_ms,
        )

    def get_intervals(self, peer_id: str) -> tuple[float, ...]:
        """Return the tracked inter-arrival intervals for one peer."""
        with self._lock:
            samples = self._intervals_s.get(peer_id, [])
            return tuple(samples)

