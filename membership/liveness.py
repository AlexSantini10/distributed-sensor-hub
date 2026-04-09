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
    """

    last_heartbeat: float
    phi: float
    status: NodeStatus

    @staticmethod
    def new(*, now: float | None = None) -> "NodeLiveness":
        """Create a healthy initial liveness state."""
        return NodeLiveness(
            last_heartbeat=time.time() if now is None else now,
            phi=0.0,
            status=NodeStatus.ALIVE,
        )
