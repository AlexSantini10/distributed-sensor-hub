"""Define the topology policy contract used by runtime networking.

Responsibilities:
    - Describe how runtime code obtains connectable peer targets.
    - Describe how runtime code selects peers to connect from current context.
    - Reserve disconnect and under-connected hooks for future policies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from topology.models import TopologyContext, TopologyPeer


class TopologyPolicy(ABC):
    """Define strategy hooks for topology-driven connection decisions."""

    @abstractmethod
    def resolve_connection_target(self, peer: TopologyPeer) -> TopologyPeer:
        """Return the concrete outbound target for one peer descriptor.

        Args:
            peer (TopologyPeer): Peer descriptor from membership or bootstrap inputs.

        Returns:
            TopologyPeer: Connectable target descriptor for outbound registration.
        """

    @abstractmethod
    def select_peers_to_connect(
        self,
        context: TopologyContext,
    ) -> tuple[TopologyPeer, ...]:
        """Select peers that should be connected given current topology context.

        Args:
            context (TopologyContext): Snapshot used to compute connect candidates.

        Returns:
            tuple[TopologyPeer, ...]: Peers that should be connected by the caller.
        """

    @abstractmethod
    def select_peers_to_disconnect(
        self,
        context: TopologyContext,
    ) -> tuple[str, ...]:
        """Select peers that should be disconnected.

        This method is a reserved extension point. Current runtime behavior does
        not perform topology-driven disconnections.

        Args:
            context (TopologyContext): Snapshot used to compute disconnect candidates.

        Returns:
            tuple[str, ...]: Node IDs that should be disconnected.
        """

    @abstractmethod
    def handle_under_connected(
        self,
        context: TopologyContext,
    ) -> tuple[TopologyPeer, ...]:
        """Return optional remediation peers when connectivity is insufficient.

        This method is a reserved extension point. Current runtime behavior does
        not execute under-connected remediation actions.

        Args:
            context (TopologyContext): Snapshot used to compute remediation actions.

        Returns:
            tuple[TopologyPeer, ...]: Additional peers that may improve connectivity.
        """
