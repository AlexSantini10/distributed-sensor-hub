import threading
from typing import Dict, List, Optional
from membership.peer import Peer


class PeerTable:
    """
    Thread-safe table of known peers.

    Responsibilities:
    - Store peer identity and liveness state
    - Insert new peers without overwriting existing state
    - Provide read-only snapshots for gossip / replies
    """

    def __init__(self, self_node_id: str):
        self._self_node_id = self_node_id
        self._lock = threading.Lock()
        self._peers: Dict[str, Peer] = {}

    def add_peer(self, peer: Peer) -> bool:
        """
        Add a new peer if not already present.

        Returns True if the peer was added,
        False if it already existed.
        """
        if peer.node_id == self._self_node_id:
            return False

        with self._lock:
            if peer.node_id in self._peers:
                return False

            self._peers[peer.node_id] = peer
            return True

    def get_peer(self, node_id: str) -> Optional[Peer]:
        with self._lock:
            return self._peers.get(node_id)

    def update_heartbeat(self, node_id: str, timestamp: float) -> None:
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return

            peer.last_heartbeat = timestamp
            peer.status = "alive"

    def list_peers(self) -> List[Peer]:
        """
        Return a snapshot list of all known peers.
        """
        with self._lock:
            return list(self._peers.values())
