"""Peer model for the membership subsystem.

Responsibilities:
- Represent a remote node's network identity and observed liveness metadata.
- Provide the canonical in-memory record exchanged indirectly through gossip
  membership handlers.
- Capture failure-detection fields used by higher-level membership logic
  without defining the failure-detection algorithm itself.
"""

from dataclasses import dataclass
from typing import Literal
import time


PeerStatus = Literal["alive", "suspected", "dead"]


@dataclass
class Peer:
    """Represent a known cluster peer.

    Attributes:
        node_id: Stable logical identifier for the remote node.
        host: Routable host or IP address used to contact the node.
        port: TCP port used by the node's protocol server.
        last_heartbeat: Unix timestamp of the latest accepted liveness signal.
        phi: Failure-detector score associated with the peer.
        status: Current liveness classification for membership decisions.
    """

    node_id: str
    host: str
    port: int

    last_heartbeat: float
    phi: float
    status: PeerStatus

    @staticmethod
    def new(node_id: str, host: str, port: int) -> "Peer":
        """Create a peer record with initial healthy liveness metadata.

        Args:
            node_id: Stable logical identifier for the peer.
            host: Routable host or IP address for the peer.
            port: TCP port exposed by the peer.

        Returns:
            Peer: New peer initialized as alive with a current heartbeat
            timestamp and zero phi score.
        """
        return Peer(
            node_id=node_id,
            host=host,
            port=port,
            last_heartbeat=time.time(),
            phi=0.0,
            status="alive",
        )
