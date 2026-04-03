"""Thread-safe membership table for known peers.

Responsibilities:
- Maintain the local node's view of discovered peers.
- Enforce idempotent insertion semantics for repeated gossip or join messages.
- Expose snapshot-style reads for membership replies and other subsystems.
- Track liveness metadata updates without defining eviction or suspicion policy.
"""

import threading
from typing import Dict, List, Optional
from membership.peer import Peer


class PeerTable:
    """Store and query known peers for the local node.

    Attributes:
        _self_node_id: Logical identifier of the local node.
        _lock: Mutex protecting peer-table mutations and reads.
        _peers: Mapping from peer node ID to the latest known peer record.
    """

    def __init__(self, self_node_id: str):
        """Initialize an empty membership table.

        Args:
            self_node_id: Logical identifier of the local node. Entries with
                this ID are rejected to avoid self-membership loops.
        """
        self._self_node_id = self_node_id
        self._lock = threading.Lock()
        self._peers: Dict[str, Peer] = {}

    def add_peer(self, peer: Peer) -> bool:
        """Insert a peer if it is new and not the local node.

        Args:
            peer: Candidate peer record derived from bootstrap or gossip input.

        Returns:
            bool: `True` if the peer was inserted, or `False` if the peer
            already existed or refers to the local node.
        """
        if peer.node_id == self._self_node_id:
            return False

        with self._lock:
            if peer.node_id in self._peers:
                return False

            self._peers[peer.node_id] = peer
            return True

    def get_peer(self, node_id: str) -> Optional[Peer]:
        """Return the current peer record for a node ID.

        Args:
            node_id: Logical identifier of the peer to look up.

        Returns:
            Optional[Peer]: The stored peer record, or `None` when the peer is
            unknown.
        """
        with self._lock:
            return self._peers.get(node_id)

    def update_heartbeat(self, node_id: str, timestamp: float) -> None:
        """Record a liveness update for an existing peer.

        Args:
            node_id: Logical identifier of the peer to refresh.
            timestamp: Accepted heartbeat timestamp in Unix seconds.

        Returns:
            None: This method updates state in place.

        Notes:
            Unknown peers are ignored. The update marks the peer as `alive`
            because the caller has accepted a fresh liveness signal.
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return

            peer.last_heartbeat = timestamp
            peer.status = "alive"

    def list_peers(self) -> List[Peer]:
        """Return a snapshot of the current membership view.

        Returns:
            List[Peer]: Shallow snapshot of peer records known at call time.

        Notes:
            The returned list is detached from future table insertions or
            removals, which makes it suitable for gossip replies.
        """
        with self._lock:
            return list(self._peers.values())
