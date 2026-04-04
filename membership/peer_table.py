"""Maintain the local membership view for discovered peers.

Responsibilities:
    - Own the single lock protecting all membership state mutations.
    - Expose atomic membership operations with typed outcomes.
    - Return snapshots rather than live mutable peer objects to callers.
    - Avoid leaking synchronization requirements into handlers or callbacks.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Dict

from membership.peer import Peer
from membership.results import (
    FailureDetectionUpdateResult,
    MembershipMergeResult,
    PeerRemovalResult,
    PeerStatusTransitionResult,
    PeerUpsertResult,
)
from membership.status import NodeStatus


class PeerTable:
    """Store and query known peers for the local node.

    Attributes:
        _self_node_id (str): Logical identifier of the local node.
        _lock (threading.Lock): Mutex protecting all membership mutations and reads.
        _peers (Dict[str, Peer]): Mapping from peer node ID to the latest known peer record.
    """

    def __init__(self, self_node_id: str):
        """Initialize an empty membership table.

        Args:
            self_node_id (str): Logical identifier of the local node. Entries
            with this ID are rejected to avoid self-membership loops.

        Returns:
            None: This initializer configures an empty peer table.
        """
        self._self_node_id = self_node_id
        self._lock = threading.Lock()
        self._peers: Dict[str, Peer] = {}

    def upsert_peer(self, *, node_id: str, host: str, port: int) -> PeerUpsertResult:
        """Insert a peer or refresh its advertised endpoint atomically."""
        if node_id == self._self_node_id:
            return PeerUpsertResult(
                peer_id=node_id,
                changed=False,
                inserted=False,
                previous_status=None,
                new_status=None,
                peer=None,
                should_gossip=False,
                reason="ignored_self",
            )

        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                created = Peer.new(node_id=node_id, host=host, port=port)
                self._peers[node_id] = created
                return PeerUpsertResult(
                    peer_id=node_id,
                    changed=True,
                    inserted=True,
                    previous_status=None,
                    new_status=created.status,
                    peer=self._clone_peer(created),
                    should_gossip=True,
                    reason="inserted",
                )

            if peer.host == host and peer.port == port:
                return PeerUpsertResult(
                    peer_id=node_id,
                    changed=False,
                    inserted=False,
                    previous_status=peer.status,
                    new_status=peer.status,
                    peer=self._clone_peer(peer),
                    should_gossip=False,
                    reason="unchanged",
                )

            peer.host = host
            peer.port = port
            return PeerUpsertResult(
                peer_id=node_id,
                changed=True,
                inserted=False,
                previous_status=peer.status,
                new_status=peer.status,
                peer=self._clone_peer(peer),
                should_gossip=True,
                reason="endpoint_updated",
            )

    def mark_suspected(
        self,
        node_id: str,
        *,
        phi: float | None = None,
    ) -> FailureDetectionUpdateResult:
        """Mark an existing peer as suspected without exposing live state."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                status_result = PeerStatusTransitionResult(
                    peer_id=node_id,
                    changed=False,
                    previous_status=None,
                    new_status=None,
                    should_gossip=False,
                    reason="peer_not_found",
                )
                return FailureDetectionUpdateResult(
                    peer_id=node_id,
                    changed=False,
                    heartbeat_advanced=False,
                    phi_updated=False,
                    peer=None,
                    status=status_result,
                    should_gossip=False,
                    reason="peer_not_found",
                )

            previous_status = peer.status
            status_changed = previous_status is not NodeStatus.SUSPECTED
            phi_updated = False
            if phi is not None:
                phi_updated = peer.phi != phi
                peer.phi = phi
            peer.status = NodeStatus.SUSPECTED
            status_result = PeerStatusTransitionResult(
                peer_id=node_id,
                changed=status_changed,
                previous_status=previous_status,
                new_status=peer.status,
                should_gossip=status_changed,
                reason="marked_suspected" if status_changed else "phi_refreshed" if phi_updated else "unchanged",
            )
            return FailureDetectionUpdateResult(
                peer_id=node_id,
                changed=status_changed or phi_updated,
                heartbeat_advanced=False,
                phi_updated=phi_updated,
                peer=self._clone_peer(peer),
                status=status_result,
                should_gossip=status_result.should_gossip,
                reason=status_result.reason,
            )

    def mark_alive(
        self,
        node_id: str,
        *,
        heartbeat_at: float,
        phi: float | None = None,
    ) -> FailureDetectionUpdateResult:
        """Mark an existing peer alive and advance heartbeat metadata atomically."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                status_result = PeerStatusTransitionResult(
                    peer_id=node_id,
                    changed=False,
                    previous_status=None,
                    new_status=None,
                    should_gossip=False,
                    reason="peer_not_found",
                )
                return FailureDetectionUpdateResult(
                    peer_id=node_id,
                    changed=False,
                    heartbeat_advanced=False,
                    phi_updated=False,
                    peer=None,
                    status=status_result,
                    should_gossip=False,
                    reason="peer_not_found",
                )

            previous_status = peer.status
            new_heartbeat = max(peer.last_heartbeat, heartbeat_at)
            new_phi = 0.0 if phi is None else phi
            heartbeat_advanced = peer.last_heartbeat != new_heartbeat
            phi_updated = peer.phi != new_phi
            status_changed = previous_status is not NodeStatus.ALIVE
            peer.last_heartbeat = new_heartbeat
            peer.phi = new_phi
            peer.status = NodeStatus.ALIVE
            status_result = PeerStatusTransitionResult(
                peer_id=node_id,
                changed=status_changed,
                previous_status=previous_status,
                new_status=peer.status,
                should_gossip=status_changed,
                reason=(
                    "marked_alive"
                    if status_changed
                    else "heartbeat_advanced"
                    if heartbeat_advanced
                    else "phi_reset"
                    if phi_updated
                    else "unchanged"
                ),
            )
            return FailureDetectionUpdateResult(
                peer_id=node_id,
                changed=status_changed or heartbeat_advanced or phi_updated,
                heartbeat_advanced=heartbeat_advanced,
                phi_updated=phi_updated,
                peer=self._clone_peer(peer),
                status=status_result,
                should_gossip=status_result.should_gossip,
                reason=status_result.reason,
            )

    def remove_peer(self, node_id: str) -> PeerRemovalResult:
        """Remove a peer atomically if it exists."""
        with self._lock:
            peer = self._peers.pop(node_id, None)
            if peer is None:
                return PeerRemovalResult(
                    peer_id=node_id,
                    changed=False,
                    peer=None,
                    should_gossip=False,
                    reason="peer_not_found",
                )
            return PeerRemovalResult(
                peer_id=node_id,
                changed=True,
                peer=self._clone_peer(peer),
                should_gossip=True,
                reason="removed",
            )

    def merge_membership_view(self, peers: Iterable[Peer]) -> MembershipMergeResult:
        """Merge an inbound membership view under a single lock."""
        added: list[Peer] = []
        updated: list[Peer] = []
        ignored_entries = 0

        with self._lock:
            for candidate in peers:
                if candidate.node_id == self._self_node_id:
                    ignored_entries += 1
                    continue

                existing = self._peers.get(candidate.node_id)
                if existing is None:
                    created = Peer.new(
                        node_id=candidate.node_id,
                        host=candidate.host,
                        port=candidate.port,
                    )
                    self._peers[candidate.node_id] = created
                    added.append(self._clone_peer(created))
                    continue

                if existing.host == candidate.host and existing.port == candidate.port:
                    continue

                existing.host = candidate.host
                existing.port = candidate.port
                updated.append(self._clone_peer(existing))

        return MembershipMergeResult(
            changed=bool(added or updated),
            merged_entries=len(added) + len(updated),
            ignored_entries=ignored_entries,
            new_peers=tuple(added),
            updated_peers=tuple(updated),
            should_gossip=bool(added or updated),
            reason="membership_view_changed" if added or updated else "unchanged",
        )

    def get_peer(self, node_id: str) -> Peer | None:
        """Return a snapshot of one peer record for a node ID."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return None
            return self._clone_peer(peer)

    def snapshot(self) -> tuple[Peer, ...]:
        """Return a full snapshot of the current membership view."""
        with self._lock:
            return tuple(self._clone_peer(peer) for peer in self._peers.values())

    def list_peers(self) -> list[Peer]:
        """Return a list snapshot for existing read-only call sites."""
        return list(self.snapshot())

    @staticmethod
    def _clone_peer(peer: Peer) -> Peer:
        """Copy a peer record before exposing it outside the lock owner."""
        return Peer(
            node_id=peer.node_id,
            host=peer.host,
            port=peer.port,
            last_heartbeat=peer.last_heartbeat,
            phi=peer.phi,
            status=peer.status,
        )
