"""Define immutable topology models used by policy decisions.

Responsibilities:
    - Provide a minimal peer model shared between runtime and topology policy.
    - Provide the topology context required to evaluate connect/disconnect choices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopologyPeer:
    """Represent one peer candidate for topology decisions.

    Attributes:
        node_id (str): Stable peer identifier.
        host (str): Advertised host for outbound connections.
        port (int): Advertised TCP port for outbound connections.
    """

    node_id: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class TopologyContext:
    """Bundle minimal runtime topology inputs for one policy evaluation.

    Attributes:
        known_peers (tuple[TopologyPeer, ...]): Peers known from membership/discovery.
        connected_peers (tuple[str, ...]): Node IDs currently registered in outbound transport.
        bootstrap_peers (tuple[TopologyPeer, ...]): Configured bootstrap peers when available.
    """

    known_peers: tuple[TopologyPeer, ...]
    connected_peers: tuple[str, ...]
    bootstrap_peers: tuple[TopologyPeer, ...]
