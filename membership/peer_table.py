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
    MergeMembershipResult,
    PeerStatusOutcome,
    PeerStatusResult,
    RemovePeerOutcome,
    RemovePeerResult,
    UpsertPeerOutcome,
    UpsertPeerResult,
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

    def upsert_peer(self, *, node_id: str, host: str, port: int) -> UpsertPeerResult:
        """Insert a peer or refresh its advertised endpoint atomically."""
        if node_id == self._self_node_id:
            return UpsertPeerResult(
                outcome=UpsertPeerOutcome.IGNORED_SELF,
                peer=None,
            )

        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                created = Peer.new(node_id=node_id, host=host, port=port)
                self._peers[node_id] = created
                return UpsertPeerResult(
                    outcome=UpsertPeerOutcome.INSERTED,
                    peer=self._clone_peer(created),
                )

            if peer.host == host and peer.port == port:
                return UpsertPeerResult(
                    outcome=UpsertPeerOutcome.UNCHANGED,
                    peer=self._clone_peer(peer),
                )

            peer.host = host
            peer.port = port
            return UpsertPeerResult(
                outcome=UpsertPeerOutcome.UPDATED,
                peer=self._clone_peer(peer),
            )

    def mark_suspected(self, node_id: str, *, phi: float | None = None) -> PeerStatusResult:
        """Mark an existing peer as suspected without exposing live state."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return PeerStatusResult(
                    outcome=PeerStatusOutcome.NOT_FOUND,
                    peer=None,
                )

            changed = peer.status is not NodeStatus.SUSPECTED
            if phi is not None:
                changed = changed or peer.phi != phi
                peer.phi = phi
            peer.status = NodeStatus.SUSPECTED
            return PeerStatusResult(
                outcome=PeerStatusOutcome.UPDATED if changed else PeerStatusOutcome.UNCHANGED,
                peer=self._clone_peer(peer),
            )

    def mark_alive(
        self,
        node_id: str,
        *,
        heartbeat_at: float,
        phi: float | None = None,
    ) -> PeerStatusResult:
        """Mark an existing peer alive and advance heartbeat metadata atomically."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return PeerStatusResult(
                    outcome=PeerStatusOutcome.NOT_FOUND,
                    peer=None,
                )

            new_heartbeat = max(peer.last_heartbeat, heartbeat_at)
            new_phi = 0.0 if phi is None else phi
            changed = (
                peer.status is not NodeStatus.ALIVE
                or peer.last_heartbeat != new_heartbeat
                or peer.phi != new_phi
            )
            peer.last_heartbeat = new_heartbeat
            peer.phi = new_phi
            peer.status = NodeStatus.ALIVE
            return PeerStatusResult(
                outcome=PeerStatusOutcome.UPDATED if changed else PeerStatusOutcome.UNCHANGED,
                peer=self._clone_peer(peer),
            )

    def remove_peer(self, node_id: str) -> RemovePeerResult:
        """Remove a peer atomically if it exists."""
        with self._lock:
            peer = self._peers.pop(node_id, None)
            if peer is None:
                return RemovePeerResult(
                    outcome=RemovePeerOutcome.NOT_FOUND,
                    peer=None,
                )
            return RemovePeerResult(
                outcome=RemovePeerOutcome.REMOVED,
                peer=self._clone_peer(peer),
            )

    def merge_membership_view(self, peers: Iterable[Peer]) -> MergeMembershipResult:
        """Merge an inbound membership view under a single lock."""
        added: list[Peer] = []
        updated: list[Peer] = []
        unchanged: list[str] = []
        ignored_self: list[str] = []

        with self._lock:
            for candidate in peers:
                if candidate.node_id == self._self_node_id:
                    ignored_self.append(candidate.node_id)
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
                    unchanged.append(candidate.node_id)
                    continue

                existing.host = candidate.host
                existing.port = candidate.port
                updated.append(self._clone_peer(existing))

        return MergeMembershipResult(
            added=tuple(added),
            updated=tuple(updated),
            unchanged=tuple(unchanged),
            ignored_self=tuple(ignored_self),
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
