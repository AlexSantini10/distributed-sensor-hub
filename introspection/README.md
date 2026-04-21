# introspection

Reusable read-only cluster introspection service and data contracts.

## Purpose

The `introspection` module provides transport-agnostic snapshots for:

- merged topology view
- membership/health view
- replicated sensor state
- recent control-plane events
- replication/gossip metrics

`webapi` can expose these snapshots over HTTP, but the same service is usable directly by tests, scripts, and debugging tools.
