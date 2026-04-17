"""Provide the peer record used by membership and gossip flows.

Responsibilities:
    - Define the canonical in-memory identity exchanged by membership messages.
    - Carry liveness metadata consumed by failure-detection and routing logic.
    - Preserve peer-address contracts independently from transport sessions.
"""

from dataclasses import dataclass

from membership.liveness import NodeLiveness
from membership.status import NodeStatus


@dataclass
class Peer:
    """Represent a known cluster peer in the local membership view.

    Attributes:
        node_id (str): Stable logical identifier for the remote node.
        host (str): Advertised host or IP address used for future connections.
        port (int): TCP port exposed by the peer's protocol server.
        liveness (NodeLiveness): Aggregated heartbeat and failure-detection state.
    """

    node_id: str
    host: str
    port: int

    liveness: NodeLiveness

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
            liveness=NodeLiveness.new(),
        )

    @property
    def last_heartbeat(self) -> float:
        """Expose heartbeat timestamp for compatibility with existing call sites."""
        return self.liveness.last_heartbeat

    @last_heartbeat.setter
    def last_heartbeat(self, value: float) -> None:
        self.liveness.last_heartbeat = value

    @property
    def phi(self) -> float:
        """Expose phi score for compatibility with existing call sites."""
        return self.liveness.phi

    @phi.setter
    def phi(self, value: float) -> None:
        self.liveness.phi = value

    @property
    def status(self) -> NodeStatus:
        """Expose node status for compatibility with existing call sites."""
        return self.liveness.status

    @status.setter
    def status(self, value: NodeStatus) -> None:
        self.liveness.status = value

    @property
    def status_ts_ms(self) -> int:
        """Expose LWW timestamp for status merges."""
        return self.liveness.status_ts_ms

    @status_ts_ms.setter
    def status_ts_ms(self, value: int) -> None:
        self.liveness.status_ts_ms = value

    @property
    def direct_observed(self) -> bool:
        """Expose whether this peer has direct transport observations."""
        return self.liveness.direct_observed

    @direct_observed.setter
    def direct_observed(self, value: bool) -> None:
        self.liveness.direct_observed = value

    @property
    def last_evidence_ts_ms(self) -> int:
        """Expose latest local evidence timestamp for this peer."""
        return self.liveness.last_evidence_ts_ms

    @last_evidence_ts_ms.setter
    def last_evidence_ts_ms(self, value: int) -> None:
        self.liveness.last_evidence_ts_ms = value

    @property
    def last_evidence_source(self) -> str:
        """Expose source of the latest local evidence update."""
        return self.liveness.last_evidence_source

    @last_evidence_source.setter
    def last_evidence_source(self, value: str) -> None:
        self.liveness.last_evidence_source = value
