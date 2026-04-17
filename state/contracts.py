"""Define state-layer contracts for merge and storage collaboration.

Responsibilities:
    - Expose abstraction boundaries for merge-capable stores used by workers.
    - Keep worker/store collaboration independent from concrete LWW implementation details.
"""

from __future__ import annotations

from typing import Literal, Protocol, TYPE_CHECKING

from utils.typing import JsonObject, NodeSnapshot, ReplicationDeltaBatch

if TYPE_CHECKING:
    from state.node_state_store import SensorRecord

StoreMergeReason = Literal["insert", "newer_ts", "tie_break", "stale"]
type StoreMergeOutcome = tuple[bool, StoreMergeReason, SensorRecord | None]


class RecordMergeStore(Protocol):
    """Define the minimal merge contract exposed by a state store."""

    def merge_record(
        self,
        sensor_id: str,
        update: "SensorRecord",
        ui_source: str = "unknown",
    ) -> StoreMergeOutcome:
        """Merge one normalized record into the store."""
        ...


class StateStoreLike(RecordMergeStore, Protocol):
    """Define the state-store behavior required by the worker."""

    def dump_full_state(self) -> JsonObject:
        """Return a deterministic inspection view grouped by winning origin."""
        ...

    def get_items_for_logging(self) -> list[tuple[str, "SensorRecord"]]:
        """Return sorted store items suitable for deterministic logging."""
        ...

    def merge_state(
        self,
        remote_full_state: JsonObject | NodeSnapshot,
        reject_partial: bool = False,
        ui_source: str = "full_sync",
    ) -> int:
        """Merge a remote snapshot into local state."""
        ...

    def remove(self, sensor_id: str) -> bool:
        """Remove one logical sensor from the store."""
        ...

    def get_state_snapshot(self, node_id: str) -> NodeSnapshot:
        """Return a full snapshot of current winning records."""
        ...

    def get_updates_snapshot(self, node_id: str) -> NodeSnapshot:
        """Drain UI-facing incremental updates."""
        ...

    def pop_replication_updates(self, node_id: str) -> NodeSnapshot:
        """Drain replication-facing snapshot updates."""
        ...

    def pop_replication_deltas(self) -> ReplicationDeltaBatch:
        """Drain ordered replication deltas."""
        ...

    def get_replication_deltas_since(
        self,
        *,
        since_ts_ms: int,
    ) -> ReplicationDeltaBatch | None:
        """Return ordered deltas newer than the supplied timestamp."""
        ...

    def get_latest_timestamp_for_origin(self, origin: str) -> int:
        """Return the max winning timestamp currently known for one origin."""
        ...
