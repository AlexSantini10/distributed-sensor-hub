"""Define shared typing contracts used across the runtime.

Responsibilities:
    - Centralize JSON-compatible value aliases reused by protocol and state code.
    - Expose structural protocols for logger-like and runtime-integrated objects.
    - Provide typed snapshot and event shapes shared across modules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, TypedDict, runtime_checkable


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


type LoggerLike = logging.Logger | logging.LoggerAdapter[logging.Logger]


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


type NodeSnapshot = dict[str, dict[str, SensorRecordDict]]


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


class StateWorkerLike(Protocol):
    """Define the subset of worker behavior used by runtime collaborators."""

    def merge_update(
        self,
        sensor_id: str,
        value: JsonValue,
        ts_ms: int,
        origin: str,
        meta: JsonObject | SensorMetaDict,
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

    def snapshot(self) -> tuple[MembershipPeer, ...]:
        """Return a snapshot of known peers.

        Returns:
            tuple[MembershipPeer, ...]: Current peer snapshot.
        """
        ...


type SenderLike = Callable[[str, "Message"], None]


class SnapshotProvider(Protocol):
    """Define the call signature used by the HTTP API snapshot endpoints."""

    def __call__(self) -> NodeSnapshot:
        """Produce a state snapshot.

        Returns:
            NodeSnapshot: Snapshot payload returned by the HTTP API.
        """
        ...


class SensorEventSource(Protocol):
    """Define the queue contract used by the state worker."""

    def get(self, timeout: float | None = None) -> SensorEvent:
        """Return the next normalized sensor event.

        Args:
            timeout (float | None): Maximum wait time in seconds.

        Returns:
            SensorEvent: Next available sensor event.
        """
        ...


if TYPE_CHECKING:
    from membership.peer import Peer as MembershipPeer
    from protocol.message import Message
    from state.events import SensorEvent
