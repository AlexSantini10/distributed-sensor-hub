# Topology Module

## Purpose

The `topology` module has two responsibilities:

- **Topology policy** for outbound connection decisions.
- **Topology state dissemination** for eventually consistent cluster-wide adjacency knowledge.

Policy keeps networking strategy pluggable. Topology state lets every node publish and merge direct-neighbor declarations learned via peer-to-peer gossip.

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
- `state.py`
  - Defines reusable disseminated topology state:
    - `TopologyEntry` with `{node_id, direct_neighbors, updated_at_ms}`.
    - `TopologyStateStore` that keeps local declaration + merged global view.
    - LWW merge per node entry with deterministic tie-break on equal version.
- `__init__.py`
  - Exposes the module public surface (`TopologyContext`, `TopologyPeer`, `TopologyPolicy`, `FullMeshTopologyPolicy`, resolver function, `TopologyEntry`, `TopologyStateStore`).

## Main Dependencies

- Internal: `utils.config.TopologyPolicyName`
  - Provides the canonical configuration enum used to validate and resolve policy selection.
- Internal: `protocol.contracts.NetworkConstant`
  - Provides the wildcard host constant used during outbound target normalization in full-mesh mode.
- Internal consumer: `runtime.networking`
  - Builds `TopologyContext`, invokes policy selection/resolution, and applies decisions to TCP peer registration.
- Internal consumers: `gossip.publisher`, `gossip.handlers`, `runtime.networking`, `runtime.heartbeat`
  - Publish and merge topology entries through `GOSSIP_STATE`.
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
  - Runtime also updates local topology declaration on connectivity changes (connect, reconnect, unavailable).
  - Gossip rounds include `state.topology.entries`.
  - Receivers merge entries with **LWW per node entry**:
    - newer `updated_at_ms` wins,
    - equal timestamp resolves deterministically by sorted neighbor tuple comparison.
  - Any component can read `TopologyStateStore.topology_snapshot()` or `get_adjacency_map()` without coupling to UI.

- **Interactions with other modules**
  - Input side: receives peer information originating from membership/discovery and bootstrap configuration (via runtime).
  - Output side: provides connect candidates and resolved endpoints consumed by networking transport assembly.
  - Configuration boundary: policy choice is controlled by configuration parsing (`TopologyPolicyName`) and resolved through `resolver.py`.
