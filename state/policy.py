"""Define merge-policy contracts for replicated sensor-state conflict resolution.

Responsibilities:
    - Expose a policy interface used by state storage to decide merge winners.
    - Provide the default Last-Write-Wins policy implementation.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from state.node_state_store import SensorRecord

MergeDecision = Literal["newer_ts", "tie_break", "stale"]


class MergePolicy(Protocol):
    """Decide whether a candidate update should replace the current winner."""

    def decide(
        self,
        *,
        current: "SensorRecord",
        candidate: "SensorRecord",
    ) -> MergeDecision:
        """Return the merge decision for one current/candidate pair."""
        ...


@dataclass(frozen=True)
class LwwMergePolicy:
    """Apply Last-Write-Wins ordering on ``(ts_ms, origin)``."""

    def decide(
        self,
        *,
        current: "SensorRecord",
        candidate: "SensorRecord",
    ) -> MergeDecision:
        if candidate.ts_ms > current.ts_ms:
            return "newer_ts"
        if candidate.ts_ms == current.ts_ms and candidate.origin > current.origin:
            return "tie_break"
        return "stale"
