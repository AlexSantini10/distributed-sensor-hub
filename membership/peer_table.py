"""Maintain the local membership view for discovered peers.

Responsibilities:
    - Own the single lock protecting all membership state mutations.
    - Expose atomic membership operations with typed outcomes.
    - Keep detector-local state separate from replicated membership state.
    - Return snapshots rather than live mutable peer objects to callers.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from typing import Dict

from fd.heartbeat import HeartbeatMonitor
from fd.status import FailureStatus
from membership.liveness import NodeLiveness
from membership.peer import Peer
from membership.results import (
    FailureDetectionUpdateResult,
    MembershipMergeResult,
    PeerRemovalResult,
    PeerStatusTransitionResult,
    PeerUpsertResult,
)
from membership.status import NodeStatus
from utils.typing import JsonObject, MembershipSnapshotDict, MembershipSnapshotPeerDict


class PeerTable:
    """Store and query known peers for the local node."""

    def __init__(
        self,
        self_node_id: str,
        *,
        phi_threshold_suspect: float = 3.0,
        phi_threshold_dead: float = 8.0,
        phi_initial_interval_s: float = 1.0,
        phi_max_intervals_per_peer: int = 128,
    ):
        """Initialize an empty membership table."""
        self._self_node_id = self_node_id
        self._lock = threading.Lock()
        self._peers: Dict[str, Peer] = {}
        self._failure_detector = HeartbeatMonitor(
            threshold_suspect=phi_threshold_suspect,
            threshold_dead=phi_threshold_dead,
            initial_interval_s=phi_initial_interval_s,
            max_intervals_per_peer=phi_max_intervals_per_peer,
        )

    @staticmethod
    def _map_failure_status(status: FailureStatus) -> NodeStatus:
        """Translate detector-local status into membership status."""
        if status is FailureStatus.DEAD:
            return NodeStatus.DEAD
        if status is FailureStatus.SUSPECTED:
            return NodeStatus.SUSPECTED
        return NodeStatus.ALIVE

    @property
    def phi_threshold_suspect(self) -> float:
        """Expose the configured suspicion threshold."""
        return self._failure_detector.threshold_suspect

    @property
    def phi_threshold_dead(self) -> float:
        """Expose the configured dead threshold."""
        return self._failure_detector.threshold_dead

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
                self._failure_detector.initialize_peer(node_id)
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

    def record_heartbeat(
        self,
        node_id: str,
        *,
        heartbeat_at: float,
        arrived_at_monotonic_s: float | None = None,
        sender_timestamp_ms: int | None = None,
    ) -> FailureDetectionUpdateResult:
        """Record a heartbeat and reset peer status to alive atomically."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return self._not_found_failure_result(node_id)

            observation = self._failure_detector.record_heartbeat(
                node_id,
                arrived_at_s=arrived_at_monotonic_s,
                sender_timestamp_ms=sender_timestamp_ms,
            )
            previous_status = peer.status
            previous_status_ts_ms = peer.status_ts_ms

            new_heartbeat = max(peer.last_heartbeat, heartbeat_at)
            heartbeat_advanced = peer.last_heartbeat != new_heartbeat
            peer.last_heartbeat = new_heartbeat

            phi_updated = peer.phi != observation.phi
            peer.phi = observation.phi

            status_changed = previous_status is not NodeStatus.ALIVE
            peer.status = NodeStatus.ALIVE

            candidate_status_ts_ms = int(heartbeat_at * 1000)
            new_status_ts_ms = self._next_status_ts_ms(
                current_ts_ms=previous_status_ts_ms,
                candidate_ts_ms=candidate_status_ts_ms,
            )
            status_ts_updated = previous_status_ts_ms != new_status_ts_ms
            peer.status_ts_ms = new_status_ts_ms

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
                    else "alive_refreshed"
                    if status_ts_updated
                    else "unchanged"
                ),
            )
            return FailureDetectionUpdateResult(
                peer_id=node_id,
                changed=status_changed or heartbeat_advanced or phi_updated or status_ts_updated,
                heartbeat_advanced=heartbeat_advanced,
                phi_updated=phi_updated,
                peer=self._clone_peer(peer),
                status=status_result,
                should_gossip=status_result.should_gossip,
                reason=status_result.reason,
            )

    def evaluate_failure_detector(
        self,
        *,
        observed_at_wall_s: float | None = None,
        observed_at_monotonic_s: float | None = None,
    ) -> tuple[FailureDetectionUpdateResult, ...]:
        """Evaluate phi-accrual status for all peers and apply transitions atomically."""
        wall_now = time.time() if observed_at_wall_s is None else observed_at_wall_s
        monotonic_now = (
            time.monotonic()
            if observed_at_monotonic_s is None
            else observed_at_monotonic_s
        )
        updates: list[FailureDetectionUpdateResult] = []

        with self._lock:
            for peer_id, peer in self._peers.items():
                evaluation = self._failure_detector.evaluate_peer(
                    peer_id,
                    observed_at_s=monotonic_now,
                )
                previous_status = peer.status
                previous_status_ts_ms = peer.status_ts_ms

                phi_updated = peer.phi != evaluation.phi
                peer.phi = evaluation.phi

                next_status = self._map_failure_status(evaluation.status)
                status_changed = previous_status is not next_status
                peer.status = next_status
                if status_changed:
                    peer.status_ts_ms = self._next_status_ts_ms(
                        current_ts_ms=previous_status_ts_ms,
                        candidate_ts_ms=int(wall_now * 1000),
                    )

                if not (status_changed or phi_updated):
                    continue

                status_result = PeerStatusTransitionResult(
                    peer_id=peer_id,
                    changed=status_changed,
                    previous_status=previous_status,
                    new_status=peer.status,
                    should_gossip=status_changed,
                    reason=(
                        "phi_transition"
                        if status_changed
                        else "phi_refreshed"
                    ),
                )
                updates.append(
                    FailureDetectionUpdateResult(
                        peer_id=peer_id,
                        changed=True,
                        heartbeat_advanced=False,
                        phi_updated=phi_updated,
                        peer=self._clone_peer(peer),
                        status=status_result,
                        should_gossip=status_result.should_gossip,
                        reason=status_result.reason,
                    )
                )

        return tuple(updates)

    def merge_membership_view(self, peers: Iterable[Peer]) -> MembershipMergeResult:
        """Merge inbound endpoint data while preserving local liveness state."""
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
                    self._failure_detector.initialize_peer(candidate.node_id)
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

    def merge_gossip_state(self, peers: Iterable[Peer]) -> MembershipMergeResult:
        """Merge status/timestamp gossip using LWW semantics."""
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
                    created.status = candidate.status
                    created.status_ts_ms = candidate.status_ts_ms
                    self._peers[candidate.node_id] = created
                    self._failure_detector.initialize_peer(candidate.node_id)
                    added.append(self._clone_peer(created))
                    continue

                peer_changed = False
                if existing.host != candidate.host or existing.port != candidate.port:
                    existing.host = candidate.host
                    existing.port = candidate.port
                    peer_changed = True

                if candidate.status_ts_ms > existing.status_ts_ms:
                    existing.status = candidate.status
                    existing.status_ts_ms = candidate.status_ts_ms
                    peer_changed = True

                if peer_changed:
                    updated.append(self._clone_peer(existing))

        return MembershipMergeResult(
            changed=bool(added or updated),
            merged_entries=len(added) + len(updated),
            ignored_entries=ignored_entries,
            new_peers=tuple(added),
            updated_peers=tuple(updated),
            should_gossip=bool(added or updated),
            reason="gossip_state_changed" if added or updated else "unchanged",
        )

    def build_gossip_state(self) -> JsonObject:
        """Build a serializable membership gossip payload."""
        with self._lock:
            peers = sorted(self._peers.values(), key=lambda peer: peer.node_id)
            return {
                "membership": {
                    "peers": [
                        {
                            "node_id": peer.node_id,
                            "host": peer.host,
                            "port": peer.port,
                            "status": peer.status.to_wire(),
                            "status_ts_ms": peer.status_ts_ms,
                        }
                        for peer in peers
                    ]
                }
            }

    def remove_peer(self, node_id: str) -> PeerRemovalResult:
        """Remove a peer atomically if it exists."""
        with self._lock:
            peer = self._peers.pop(node_id, None)
            self._failure_detector.remove_peer(node_id)
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

    def membership_snapshot(self) -> MembershipSnapshotDict:
        """Return a thread-safe, read-only Phi-driven membership snapshot."""
        with self._lock:
            peers = sorted(self._peers.values(), key=lambda peer: peer.node_id)
            snapshot_peers: list[MembershipSnapshotPeerDict] = []
            window_size = self._failure_detector.max_intervals_per_peer
            for peer in peers:
                sample_count = len(self._failure_detector.get_intervals(peer.node_id))
                snapshot_peers.append(
                    {
                        "peer_id": peer.node_id,
                        "host": peer.host,
                        "port": peer.port,
                        "status": peer.status.to_wire(),
                        "phi": peer.phi,
                        "last_heartbeat_ts_ms": int(peer.last_heartbeat * 1000),
                        "sample_count": sample_count,
                        "sample_window_size": window_size,
                        "status_transition_ts_ms": peer.status_ts_ms,
                    }
                )
            return {"local_node_id": self._self_node_id, "peers": snapshot_peers}

    def list_peers(self) -> list[Peer]:
        """Return a list snapshot for existing read-only call sites."""
        return list(self.snapshot())

    def _not_found_failure_result(self, node_id: str) -> FailureDetectionUpdateResult:
        """Build a no-op failure-detection result for unknown peers."""
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

    @staticmethod
    def _next_status_ts_ms(*, current_ts_ms: int, candidate_ts_ms: int) -> int:
        """Return the next monotonic local status timestamp."""
        if candidate_ts_ms > current_ts_ms:
            return candidate_ts_ms
        return current_ts_ms + 1

    @staticmethod
    def _clone_peer(peer: Peer) -> Peer:
        """Copy a peer record before exposing it outside the lock owner."""
        return Peer(
            node_id=peer.node_id,
            host=peer.host,
            port=peer.port,
            liveness=NodeLiveness(
                last_heartbeat=peer.last_heartbeat,
                phi=peer.phi,
                status=peer.status,
                status_ts_ms=peer.status_ts_ms,
            ),
        )
