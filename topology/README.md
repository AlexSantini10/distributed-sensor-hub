# Topology Module

## Purpose

The `topology` module defines the **topology-policy layer** used to drive outbound peer-connection decisions.

Its role in the overall system is to decouple runtime networking from specific peer-selection strategies. Runtime code provides a topology context (known peers, already connected peers, bootstrap peers), and this module returns policy decisions for connection targets and candidate peers.

## File Overview

- `models.py`
  - Defines immutable policy data models:
    - `TopologyPeer` (node identifier and advertised endpoint).
    - `TopologyContext` (known peers, connected peer IDs, bootstrap peers).
- `policy.py`
  - Defines the abstract `TopologyPolicy` contract:
    - target resolution (`resolve_connection_target`),
    - connect selection (`select_peers_to_connect`),
    - reserved extension hooks for disconnect and under-connected handling.
- `full_mesh.py`
  - Implements `FullMeshTopologyPolicy`, the default policy:
    - selects all non-connected peers from known and bootstrap sets,
    - deduplicates by node ID,
    - rewrites wildcard host (`0.0.0.0`) to node ID for connectability,
    - keeps disconnect/remediation hooks as no-op.
- `resolver.py`
  - Maps configured policy names to concrete `TopologyPolicy` instances and validates allowed values.
- `__init__.py`
  - Exposes the module public surface (`TopologyContext`, `TopologyPeer`, `TopologyPolicy`, `FullMeshTopologyPolicy`, resolver function).

## Main Dependencies

- Internal: `utils.config.TopologyPolicyName`
  - Provides the canonical configuration enum used to validate and resolve policy selection.
- Internal: `protocol.contracts.NetworkConstant`
  - Provides the wildcard host constant used during outbound target normalization in full-mesh mode.
- Internal consumer: `runtime.networking`
  - Builds `TopologyContext`, invokes policy selection/resolution, and applies decisions to TCP peer registration.
- External (standard library): `dataclasses`, `abc`
  - Support immutable data models and abstract policy interfaces.

## High-Level Design

- **Core responsibilities**
  - Define a stable policy contract for topology decisions.
  - Represent topology decision inputs as immutable snapshots.
  - Provide a default full-mesh policy consistent with current runtime behavior.
  - Centralize policy instantiation from configuration.

- **Main data flow**
  - Runtime collects membership-discovered peers and configured bootstrap peers.
  - Runtime builds `TopologyContext` and calls `select_peers_to_connect`.
  - For each selected peer, runtime calls `resolve_connection_target`.
  - Runtime registers resolved targets in the outbound TCP client.
  - Disconnect and under-connected hooks are currently invoked as extension points but return empty results in full-mesh mode.

- **Interactions with other modules**
  - Input side: receives peer information originating from membership/discovery and bootstrap configuration (via runtime).
  - Output side: provides connect candidates and resolved endpoints consumed by networking transport assembly.
  - Configuration boundary: policy choice is controlled by configuration parsing (`TopologyPolicyName`) and resolved through `resolver.py`.
