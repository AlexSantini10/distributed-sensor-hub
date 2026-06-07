"""Provide the canonical liveness state tracked for each known peer.

Responsibilities:
    - Keep heartbeat timestamp, phi score, and status together as one concept.
    - Encapsulate liveness initialization defaults used across membership flows.
"""

from __future__ import annotations

from dataclasses import dataclass
import time

from membership.status import NodeStatus


@dataclass(slots=True)
class NodeLiveness:
    """Represent the mutable liveness state of one peer.

    Attributes:
        last_heartbeat (float): Unix timestamp of the latest accepted heartbeat.
        phi (float): Current failure-detector score for the peer.
        status (NodeStatus): Derived liveness classification used by membership.
        status_ts_ms (int): LWW timestamp of the last status transition.
        direct_observed (bool): Whether this node has been observed on a direct transport path.
        last_evidence_ts_ms (int): Latest locally observed evidence timestamp for this peer.
        last_evidence_source (str): Source label describing the last evidence update.
    """

    last_heartbeat: float
    phi: float
    status: NodeStatus
    status_ts_ms: int
    direct_observed: bool = False
    last_evidence_ts_ms: int = 0
    last_evidence_source: str = "none"

    @staticmethod
    def new(
        *,
        now: float | None = None,
        status_ts_ms: int | None = None,
        direct_observed: bool = False,
    ) -> "NodeLiveness":
        """Create a healthy initial liveness state."""
        heartbeat_now = time.time() if now is None else now
        status_now = int(heartbeat_now * 1000) if status_ts_ms is None else status_ts_ms
        return NodeLiveness(
            last_heartbeat=heartbeat_now,
            phi=0.0,
            status=NodeStatus.ALIVE,
            status_ts_ms=status_now,
            direct_observed=direct_observed,
            last_evidence_ts_ms=status_now if direct_observed else 0,
            last_evidence_source="direct_bootstrap" if direct_observed else "none",
        )
