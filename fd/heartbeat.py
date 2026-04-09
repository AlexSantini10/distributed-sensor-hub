"""Track heartbeat arrivals and derive phi-accrual liveness outputs.

Responsibilities:
    - Record per-peer heartbeat arrivals under thread-safe access.
    - Keep bounded inter-arrival history for phi-accrual estimation.
    - Classify peers as alive/suspected/dead using phi thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from fd.phi_estimator import ExponentialPhiEstimator, PhiEstimator
from membership.status import NodeStatus


@dataclass(frozen=True, slots=True)
class HeartbeatObservation:
    """Describe one accepted heartbeat arrival."""

    peer_id: str
    arrived_at_s: float
    interval_s: float | None
    sender_timestamp_ms: int | None
    phi: float
    status: NodeStatus


@dataclass(frozen=True, slots=True)
class PhiEvaluation:
    """Describe one phi-accrual evaluation for a peer."""

    peer_id: str
    phi: float
    status: NodeStatus


class HeartbeatMonitor:
    """Store heartbeat arrivals and expose phi-accrual classifications."""

    def __init__(
        self,
        *,
        max_intervals_per_peer: int = 128,
        threshold_suspect: float = 3.0,
        threshold_dead: float = 8.0,
        initial_interval_s: float = 1.0,
        phi_estimator: PhiEstimator | None = None,
    ) -> None:
        """Initialize the monitor with bounded history and phi thresholds."""
        if threshold_suspect < 0.0:
            raise ValueError("threshold_suspect must be >= 0")
        if threshold_dead < threshold_suspect:
            raise ValueError("threshold_dead must be >= threshold_suspect")
        if max_intervals_per_peer <= 0:
            raise ValueError("max_intervals_per_peer must be > 0")
        if initial_interval_s <= 0.0:
            raise ValueError("initial_interval_s must be > 0")

        self._lock = threading.Lock()
        self._max_intervals_per_peer = max_intervals_per_peer
        self._threshold_suspect = threshold_suspect
        self._threshold_dead = threshold_dead
        self._initial_interval_s = initial_interval_s
        self._phi_estimator: PhiEstimator = (
            ExponentialPhiEstimator() if phi_estimator is None else phi_estimator
        )
        self._last_arrival_s: dict[str, float] = {}
        self._intervals_s: dict[str, list[float]] = {}

    @property
    def threshold_suspect(self) -> float:
        """Return the configured phi threshold for suspicion."""
        return self._threshold_suspect

    @property
    def threshold_dead(self) -> float:
        """Return the configured phi threshold for death."""
        return self._threshold_dead

    @property
    def max_intervals_per_peer(self) -> int:
        """Return the configured sliding-window size for heartbeat intervals."""
        return self._max_intervals_per_peer

    def initialize_peer(
        self,
        peer_id: str,
        *,
        observed_at_s: float | None = None,
    ) -> None:
        """Seed detector state for a peer that was just discovered."""
        arrival = time.monotonic() if observed_at_s is None else observed_at_s
        with self._lock:
            self._last_arrival_s.setdefault(peer_id, arrival)
            self._intervals_s.setdefault(peer_id, [])

    def remove_peer(self, peer_id: str) -> None:
        """Drop detector state for one peer."""
        with self._lock:
            self._last_arrival_s.pop(peer_id, None)
            self._intervals_s.pop(peer_id, None)

    def record_heartbeat(
        self,
        peer_id: str,
        *,
        arrived_at_s: float | None = None,
        sender_timestamp_ms: int | None = None,
    ) -> HeartbeatObservation:
        """Record one heartbeat and classify the peer as alive."""
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
            phi = 0.0
            status = NodeStatus.ALIVE

        return HeartbeatObservation(
            peer_id=peer_id,
            arrived_at_s=arrival,
            interval_s=interval,
            sender_timestamp_ms=sender_timestamp_ms,
            phi=phi,
            status=status,
        )

    def get_intervals(self, peer_id: str) -> tuple[float, ...]:
        """Return the tracked inter-arrival intervals for one peer."""
        with self._lock:
            samples = self._intervals_s.get(peer_id, [])
            return tuple(samples)

    def evaluate_peer(
        self,
        peer_id: str,
        *,
        observed_at_s: float | None = None,
    ) -> PhiEvaluation:
        """Compute the current phi and status for one peer."""
        now = time.monotonic() if observed_at_s is None else observed_at_s
        with self._lock:
            phi = self._compute_phi_locked(peer_id=peer_id, observed_at_s=now)
        return PhiEvaluation(
            peer_id=peer_id,
            phi=phi,
            status=self.classify_phi(phi),
        )

    def evaluate_all(
        self,
        *,
        observed_at_s: float | None = None,
    ) -> tuple[PhiEvaluation, ...]:
        """Compute phi and status for all peers with detector state."""
        now = time.monotonic() if observed_at_s is None else observed_at_s
        with self._lock:
            peer_ids = tuple(self._last_arrival_s.keys())
            evaluations: list[PhiEvaluation] = []
            for peer_id in peer_ids:
                phi = self._compute_phi_locked(peer_id=peer_id, observed_at_s=now)
                evaluations.append(
                    PhiEvaluation(
                        peer_id=peer_id,
                        phi=phi,
                        status=self.classify_phi(phi),
                    )
                )
        return tuple(evaluations)

    def classify_phi(self, phi: float) -> NodeStatus:
        """Classify one phi score into membership status."""
        if phi >= self._threshold_dead:
            return NodeStatus.DEAD
        if phi >= self._threshold_suspect:
            return NodeStatus.SUSPECTED
        return NodeStatus.ALIVE

    def _compute_phi_locked(self, *, peer_id: str, observed_at_s: float) -> float:
        """Compute phi for one peer. Caller must hold ``_lock``."""
        last_arrival = self._last_arrival_s.get(peer_id)
        if last_arrival is None:
            return 0.0

        elapsed = max(0.0, observed_at_s - last_arrival)
        intervals = self._intervals_s.get(peer_id)
        intervals_snapshot = tuple(intervals) if intervals else ()
        return self._phi_estimator.compute_phi(
            elapsed_s=elapsed,
            intervals_s=intervals_snapshot,
            initial_interval_s=self._initial_interval_s,
        )

