"""Resolve configured topology-policy names to concrete policy instances.

Responsibilities:
    - Centralize policy-name validation and instantiation.
    - Keep runtime wiring independent from specific topology policy classes.
"""

from __future__ import annotations

from topology.full_mesh import FullMeshTopologyPolicy
from topology.policy import TopologyPolicy
from utils.config import TopologyPolicyName


def resolve_topology_policy(policy_name: str) -> TopologyPolicy:
    """Build one topology-policy instance from configuration text.

    Args:
        policy_name (str): Policy name loaded from runtime configuration.

    Returns:
        TopologyPolicy: Policy implementation matching the configured name.

    Raises:
        RuntimeError: If the policy name is not recognized.
    """
    try:
        normalized = TopologyPolicyName(policy_name)
    except ValueError as exc:
        allowed = ", ".join(name.value for name in TopologyPolicyName)
        raise RuntimeError(
            f"Invalid TOPOLOGY_POLICY: {policy_name} (allowed: {allowed})"
        ) from exc

    if normalized is TopologyPolicyName.FULL_MESH:
        return FullMeshTopologyPolicy()

    allowed = ", ".join(name.value for name in TopologyPolicyName)
    raise RuntimeError(
        f"Invalid TOPOLOGY_POLICY: {policy_name} (allowed: {allowed})"
    )
