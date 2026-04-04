"""Define typed outcomes for thread-safe membership operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from membership.peer import Peer


class UpsertPeerOutcome(StrEnum):
    """Enumerate outcomes for peer insertion or endpoint refresh."""

    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    IGNORED_SELF = "ignored_self"


@dataclass(frozen=True)
class UpsertPeerResult:
    """Describe the result of inserting or refreshing a peer entry."""

    outcome: UpsertPeerOutcome
    peer: Peer | None


class PeerStatusOutcome(StrEnum):
    """Enumerate outcomes for liveness transitions."""

    UPDATED = "updated"
    UNCHANGED = "unchanged"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class PeerStatusResult:
    """Describe the result of a liveness mutation."""

    outcome: PeerStatusOutcome
    peer: Peer | None


class RemovePeerOutcome(StrEnum):
    """Enumerate outcomes for peer removal."""

    REMOVED = "removed"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class RemovePeerResult:
    """Describe the result of removing a peer."""

    outcome: RemovePeerOutcome
    peer: Peer | None


@dataclass(frozen=True)
class MergeMembershipResult:
    """Describe the result of merging an inbound membership view."""

    added: tuple[Peer, ...]
    updated: tuple[Peer, ...]
    unchanged: tuple[str, ...]
    ignored_self: tuple[str, ...]
