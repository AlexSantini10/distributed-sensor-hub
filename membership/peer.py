from dataclasses import dataclass
from typing import Literal
import time


PeerStatus = Literal["alive", "suspected", "dead"]


@dataclass
class Peer:
    node_id: str
    host: str
    port: int

    last_heartbeat: float
    phi: float
    status: PeerStatus

    @staticmethod
    def new(node_id: str, host: str, port: int) -> "Peer":
        return Peer(
            node_id=node_id,
            host=host,
            port=port,
            last_heartbeat=time.time(),
            phi=0.0,
            status="alive",
        )
