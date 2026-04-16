"""Provide topology-policy abstractions for connection decision flows.

Responsibilities:
    - Define policy-facing context and peer models for topology decisions.
    - Expose the policy interface consumed by runtime networking assembly.
    - Provide resolver and default full-mesh policy implementations.
"""

from topology.models import TopologyContext, TopologyPeer
from topology.policy import TopologyPolicy
from topology.full_mesh import FullMeshTopologyPolicy
from topology.resolver import resolve_topology_policy

__all__ = [
    "TopologyContext",
    "TopologyPeer",
    "TopologyPolicy",
    "FullMeshTopologyPolicy",
    "resolve_topology_policy",
]
