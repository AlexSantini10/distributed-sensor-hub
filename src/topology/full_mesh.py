"""Provide the default full-mesh topology policy.

Responsibilities:
    - Preserve current behavior where known and bootstrap peers are connect targets.
    - Keep disconnect and under-connected hooks as no-op placeholders.
"""

from __future__ import annotations

from topology.constants import WILDCARD_HOST
from topology.models import TopologyContext, TopologyPeer
from topology.policy import TopologyPolicy


class FullMeshTopologyPolicy(TopologyPolicy):
    """Implement current full-mesh semantics without behavior changes."""

    def resolve_connection_target(self, peer: TopologyPeer) -> TopologyPeer:
        """Resolve one connectable peer target.

        Args:
            peer (TopologyPeer): Source peer descriptor.

        Returns:
            TopologyPeer: Descriptor with resolved connect host.
        """
        if peer.host == WILDCARD_HOST:
            return TopologyPeer(
                node_id=peer.node_id,
                host=peer.node_id,
                port=peer.port,
            )
        return peer

    def select_peers_to_connect(
        self,
        context: TopologyContext,
    ) -> tuple[TopologyPeer, ...]:
        """Select all unknown peers from known and bootstrap sets.

        Args:
            context (TopologyContext): Topology inputs for one decision round.

        Returns:
            tuple[TopologyPeer, ...]: Peers not already connected by node ID.
        """
        connected = set(context.connected_peers)
        selected: list[TopologyPeer] = []
        seen: set[str] = set()

        for peer in context.known_peers + context.bootstrap_peers:
            if peer.node_id in connected or peer.node_id in seen:
                continue
            selected.append(peer)
            seen.add(peer.node_id)

        return tuple(selected)

    def select_peers_to_disconnect(
        self,
        context: TopologyContext,
    ) -> tuple[str, ...]:
        """Return no disconnect candidates for full-mesh behavior.

        Args:
            context (TopologyContext): Topology inputs for one decision round.

        Returns:
            tuple[str, ...]: Empty tuple for no-op disconnect behavior.
        """
        _ = context
        return ()

    def handle_under_connected(
        self,
        context: TopologyContext,
    ) -> tuple[TopologyPeer, ...]:
        """Return no remediation peers for current behavior.

        Args:
            context (TopologyContext): Topology inputs for one decision round.

        Returns:
            tuple[TopologyPeer, ...]: Empty tuple for no-op remediation behavior.
        """
        _ = context
        return ()
