"""Validate topology-policy foundations and full-mesh compatibility behavior."""

from __future__ import annotations

import pytest

from topology.full_mesh import FullMeshTopologyPolicy
from topology.models import TopologyContext, TopologyPeer
from topology.resolver import resolve_topology_policy
from utils.config import TopologyPolicyName


def test_full_mesh_selects_unknown_peers_from_known_and_bootstrap() -> None:
    """Assert full-mesh policy selects connect candidates not already connected."""
    policy = FullMeshTopologyPolicy()
    context = TopologyContext(
        known_peers=(
            TopologyPeer(node_id="node-b", host="10.0.0.2", port=9002),
            TopologyPeer(node_id="node-c", host="10.0.0.3", port=9003),
        ),
        connected_peers=("node-b",),
        bootstrap_peers=(
            TopologyPeer(node_id="bootstrap@10.0.0.4:9004", host="10.0.0.4", port=9004),
        ),
    )

    selected = policy.select_peers_to_connect(context)

    assert selected == (
        TopologyPeer(node_id="node-c", host="10.0.0.3", port=9003),
        TopologyPeer(
            node_id="bootstrap@10.0.0.4:9004",
            host="10.0.0.4",
            port=9004,
        ),
    )


def test_full_mesh_resolve_connection_target_rewrites_wildcard_host() -> None:
    """Assert wildcard advertised host resolves to node ID for outbound connect."""
    policy = FullMeshTopologyPolicy()

    target = policy.resolve_connection_target(
        TopologyPeer(node_id="node-b", host="0.0.0.0", port=9002)
    )

    assert target == TopologyPeer(node_id="node-b", host="node-b", port=9002)


def test_full_mesh_disconnect_and_under_connected_are_noop() -> None:
    """Assert current full-mesh placeholders do not request new behavior."""
    policy = FullMeshTopologyPolicy()
    context = TopologyContext(
        known_peers=(TopologyPeer(node_id="node-b", host="10.0.0.2", port=9002),),
        connected_peers=(),
        bootstrap_peers=(),
    )

    assert policy.select_peers_to_disconnect(context) == ()
    assert policy.handle_under_connected(context) == ()


def test_topology_policy_resolver_returns_full_mesh() -> None:
    """Assert resolver maps full_mesh name to default policy implementation."""
    policy = resolve_topology_policy(TopologyPolicyName.FULL_MESH.value)

    assert isinstance(policy, FullMeshTopologyPolicy)


def test_topology_policy_resolver_rejects_unknown_policy() -> None:
    """Assert resolver rejects unsupported topology policy names."""
    with pytest.raises(RuntimeError):
        resolve_topology_policy("unknown")
