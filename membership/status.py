"""Define discrete node-liveness states used by membership components."""

from __future__ import annotations

from enum import StrEnum


class NodeStatus(StrEnum):
    """Represent the derived liveness state of a known node."""

    ALIVE = "alive"
    SUSPECTED = "suspected"
    DEAD = "dead"

    def to_wire(self) -> str:
        """Return the stable serialized form used on JSON boundaries."""
        return str(self)

    @classmethod
    def from_wire(cls, raw: str) -> "NodeStatus":
        """Parse a serialized node status."""
        return cls(raw)
