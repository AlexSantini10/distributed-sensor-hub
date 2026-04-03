"""Provide the peer record used by membership and gossip flows.

Responsibilities:
    - Define the canonical in-memory identity exchanged by membership messages.
    - Carry liveness metadata consumed by failure-detection and routing logic.
    - Preserve peer-address contracts independently from transport sessions.
"""

from dataclasses import dataclass
from typing import Literal
import time


PeerStatus = Literal["alive", "suspected", "dead"]


@dataclass
class Peer:
    """Represent a known cluster peer in the local membership view.

    Attributes:
        node_id (str): Stable logical identifier for the remote node.
        host (str): Advertised host or IP address used for future connections.
        port (int): TCP port exposed by the peer's protocol server.
        last_heartbeat (float): Unix timestamp of the latest accepted liveness signal.
        phi (float): Failure-detector score associated with the peer.
        status (PeerStatus): Current liveness classification for membership decisions.
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
            node_id (str): Stable logical identifier for the peer.
            host (str): Advertised host or IP address for the peer.
            port (int): TCP port exposed by the peer.

        Returns:
            Peer: New peer initialized as alive with a current heartbeat timestamp
            and zero phi score.
        """
        return Peer(
            node_id=node_id,
            host=host,
            port=port,
            last_heartbeat=time.time(),
            phi=0.0,
            status="alive",
        )
