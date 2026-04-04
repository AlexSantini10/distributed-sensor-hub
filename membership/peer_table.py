"""Maintain the local membership view for discovered peers.

Responsibilities:
    - Store the node's current peer set with thread-safe access.
    - Enforce additive, idempotent insertion for repeated join or gossip input.
    - Expose snapshot reads used by membership replies and replication senders.
    - Track liveness metadata without defining suspicion or eviction policy.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional
from membership.peer import Peer
from membership.status import NodeStatus


class PeerTable:
    """Store and query known peers for the local node.

    Attributes:
        _self_node_id (str): Logical identifier of the local node.
        _lock (threading.Lock): Mutex protecting peer-table mutations and reads.
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

    def add_peer(self, peer: Peer) -> bool:
        """Insert a peer if it is new and not the local node.

        Args:
            peer (Peer): Candidate peer record derived from bootstrap or gossip input.

        Returns:
            bool: True if the peer was inserted, or False if the peer already
            existed or refers to the local node.
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
            node_id (str): Logical identifier of the peer to look up.

        Returns:
            Optional[Peer]: The stored peer record, or None when the peer is unknown.
        """
        with self._lock:
            return self._peers.get(node_id)

    def update_heartbeat(self, node_id: str, timestamp: float) -> None:
        """Record a liveness update for an existing peer.

        Args:
            node_id (str): Logical identifier of the peer to refresh.
            timestamp (float): Accepted heartbeat timestamp in Unix seconds.

        Returns:
            None: This method updates state in place.
        """
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return

            peer.last_heartbeat = timestamp
            peer.status = NodeStatus.ALIVE

    def list_peers(self) -> List[Peer]:
        """Return a snapshot of the current membership view.

        Returns:
            List[Peer]: Shallow snapshot of peer records known at call time.
        """
        with self._lock:
            return [
                Peer(
                    node_id=peer.node_id,
                    host=peer.host,
                    port=peer.port,
                    last_heartbeat=peer.last_heartbeat,
                    phi=peer.phi,
                    status=peer.status,
                )
                for peer in self._peers.values()
            ]
