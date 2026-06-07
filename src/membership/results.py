"""Define typed result contracts for membership and failure-detection updates."""

from __future__ import annotations

from dataclasses import dataclass

from membership.peer import Peer
from membership.status import NodeStatus


@dataclass(frozen=True, slots=True)
class PeerStatusTransitionResult:
    """Describe whether a peer changed liveness state."""

    peer_id: str
    changed: bool
    previous_status: NodeStatus | None
    new_status: NodeStatus | None
    should_gossip: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PeerUpsertResult:
    """Describe whether a peer record was inserted or refreshed."""

    peer_id: str
    changed: bool
    inserted: bool
    previous_status: NodeStatus | None
    new_status: NodeStatus | None
    peer: Peer | None
    should_gossip: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MembershipMergeResult:
    """Describe what changed while merging an inbound membership view."""

    changed: bool
    merged_entries: int
    ignored_entries: int
    new_peers: tuple[Peer, ...]
    updated_peers: tuple[Peer, ...]
    should_gossip: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class FailureDetectionUpdateResult:
    """Describe one failure-detection driven update for a peer."""

    peer_id: str
    changed: bool
    heartbeat_advanced: bool
    phi_updated: bool
    peer: Peer | None
    status: PeerStatusTransitionResult
    should_gossip: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PeerRemovalResult:
    """Describe whether a peer was removed from membership."""

    peer_id: str
    changed: bool
    peer: Peer | None
    should_gossip: bool
    reason: str | None = None
