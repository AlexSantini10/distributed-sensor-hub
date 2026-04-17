"""Define shared typing contracts used across the runtime.

Responsibilities:
    - Centralize JSON-compatible value aliases reused by protocol and state code.
    - Expose structural protocols for logger-like and runtime-integrated objects.
    - Provide typed snapshot and event shapes shared across modules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NotRequired, Protocol, TypedDict, runtime_checkable


type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | JsonObject | JsonArray
type JsonObject = dict[str, JsonValue]
type JsonArray = list[JsonValue]


@runtime_checkable
class SupportsToBytes(Protocol):
    """Define the transport contract for objects with custom byte encoding."""

    def to_bytes(self) -> bytes:
        """Serialize the object into transport bytes.

        Returns:
            bytes: Binary representation accepted by the TCP transport.
        """
        ...


@runtime_checkable
class LoggerLike(Protocol):
    """Define the logger surface consumed across runtime modules and tests."""

    debug: Callable[..., None]
    info: Callable[..., None]
    warning: Callable[..., None]
    error: Callable[..., None]
    critical: Callable[..., None]


class SensorMetaDict(TypedDict):
    """Represent normalized metadata carried with a sensor update."""

    unit: JsonValue
    period_ms: JsonValue


class SensorEventDict(TypedDict):
    """Represent the canonical sensor event shape sent into state ingestion."""

    sensor_id: str
    value: JsonValue
    ts_ms: int
    meta: SensorMetaDict


class SensorRecordDict(TypedDict):
    """Represent a materialized LWW record in snapshots and replication."""

    value: JsonValue
    ts_ms: int
    origin: str
    meta: SensorMetaDict
    sync_source: NotRequired[str]


type NodeSnapshot = dict[str, dict[str, SensorRecordDict]]


class ReplicationDeltaDict(TypedDict):
    """Represent one ordered replication delta event."""

    sensor_id: str
    value: JsonValue
    ts_ms: int
    origin: str
    meta: SensorMetaDict


type ReplicationDeltaBatch = tuple[ReplicationDeltaDict, ...]


class MembershipPeerDict(TypedDict):
    """Represent one peer entry exchanged in membership payloads."""

    node_id: str
    host: str
    port: int


class JoinRequestPayload(TypedDict):
    """Represent a membership join payload."""

    node_id: str
    host: str
    port: int


class PeerListPayload(TypedDict):
    """Represent a membership peer-list payload."""

    peers: list[MembershipPeerDict]


class SensorUpdatePayload(TypedDict):
    """Represent a replicated sensor-update payload."""

    sensor_id: str
    value: JsonValue
    ts_ms: int
    origin: str
    meta: SensorMetaDict


class MembershipSnapshotPeerDict(TypedDict):
    """Represent one peer row exposed by the membership snapshot endpoint."""

    peer_id: str
    host: str
    port: int
    status: str
    phi: float
    last_heartbeat_ts_ms: int
    sample_count: int
    sample_window_size: int
    status_transition_ts_ms: int
    direct_status: str
    evidence_status: str
    display_status: str
    last_evidence_ts_ms: int
    last_evidence_source: str
    direct_observed: bool


class MembershipSnapshotDict(TypedDict):
    """Represent the read-only Phi-based membership snapshot payload."""

    local_node_id: str
    peers: list[MembershipSnapshotPeerDict]


class StateWorkerLike(Protocol):
    """Define the subset of worker behavior used by runtime collaborators."""

    def merge_update(
        self,
        sensor_id: str,
        value: JsonValue,
        ts_ms: int,
        origin: str,
        meta: JsonObject | SensorMetaDict,
        source: str = "unknown",
    ) -> bool:
        """Attempt an LWW merge for one sensor update.

        Args:
            sensor_id (str): Logical sensor identifier.
            value (JsonValue): Candidate sensor value.
            ts_ms (int): Candidate timestamp in milliseconds.
            origin (str): Candidate origin node identifier.
            meta (JsonObject | SensorMetaDict): Candidate metadata payload.

        Returns:
            bool: ``True`` when the candidate becomes the winning record.
        """
        ...

    def get_state_snapshot(self) -> NodeSnapshot:
        """Return a full state snapshot.

        Returns:
            NodeSnapshot: Snapshot grouped by node and global sensor identifier.
        """
        ...

    def merge_state(
        self,
        remote_full_state: JsonObject | NodeSnapshot,
        reject_partial: bool = False,
    ) -> int:
        """Merge a full-state payload into local LWW state.

        Args:
            remote_full_state (JsonObject): Full-state snapshot received from a peer.
            reject_partial (bool): Whether malformed entries should reject the full merge.

        Returns:
            int: Number of sensor winners updated locally.
        """
        ...

    def get_updates_snapshot(self) -> NodeSnapshot:
        """Return incremental UI updates.

        Returns:
            NodeSnapshot: Snapshot grouped by node and global sensor identifier.
        """
        ...

    def pop_replication_updates(self) -> NodeSnapshot:
        """Return incremental replication updates.

        Returns:
            NodeSnapshot: Snapshot grouped by node and global sensor identifier.
        """
        ...

    def pop_replication_deltas(self) -> ReplicationDeltaBatch:
        """Return ordered replication deltas from the internal ring buffer.

        Returns:
            ReplicationDeltaBatch: Ordered delta events not yet consumed by gossip publication.
        """
        ...

    def get_replication_deltas_since(
        self,
        *,
        since_ts_ms: int,
    ) -> ReplicationDeltaBatch | None:
        """Return ordered deltas newer than ``since_ts_ms`` without draining.

        Returns:
            ReplicationDeltaBatch | None: Ordered delta events or ``None`` when
                the cursor is outside retained bounded history.
        """
        ...

    def get_latest_timestamp_for_origin(self, origin: str) -> int:
        """Return the latest winning timestamp currently known for one origin.

        Returns:
            int: Maximum ``ts_ms`` for records whose winner origin matches ``origin``.
        """
        ...

    def start(self) -> None:
        """Start the worker.

        Returns:
            None: This method starts background processing.
        """
        ...

    def stop(self) -> None:
        """Stop the worker.

        Returns:
            None: This method signals background processing to stop.
        """
        ...


class PeerTableLike(Protocol):
    """Define the membership-table behavior consumed outside the package."""

    def snapshot(self) -> tuple["PeerLike", ...]:
        """Return a snapshot of known peers.

        Returns:
            tuple[PeerLike, ...]: Current peer snapshot.
        """
        ...


@runtime_checkable
class PeerLike(Protocol):
    """Define the minimal peer surface used by runtime publishers."""

    node_id: str
    host: str
    port: int


type SenderLike = Callable[[str, SupportsToBytes], None]


class SnapshotProvider(Protocol):
    """Define the call signature used by the HTTP API snapshot endpoints."""

    def __call__(self) -> NodeSnapshot:
        """Produce a state snapshot.

        Returns:
            NodeSnapshot: Snapshot payload returned by the HTTP API.
        """
        ...


class MembershipSnapshotProvider(Protocol):
    """Define the call signature used by the HTTP membership endpoint."""

    def __call__(self) -> MembershipSnapshotDict:
        """Produce a membership snapshot payload.

        Returns:
            MembershipSnapshotDict: Phi-based membership snapshot.
        """
        ...


class SensorEventSource(Protocol):
    """Define the queue contract used by the state worker."""

    def get(self, timeout: float | None = None) -> object:
        """Return the next normalized sensor event.

        Args:
            timeout (float | None): Maximum wait time in seconds.

        Returns:
            object: Next available sensor event.
        """
        ...


class ReplicationDeltaSourceLike(Protocol):
    """Define the subset needed by GET_DELTA protocol handler."""

    def get_replication_deltas_since(
        self,
        *,
        since_ts_ms: int,
    ) -> ReplicationDeltaBatch | None:
        """Return ordered deltas newer than ``since_ts_ms`` without draining."""
        ...

