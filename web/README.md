# Observability UI (`web/`)

Single-page cluster observability dashboard that consumes the existing introspection contract:

- `GET /api/introspection`
- schema `introspection/v1`

No UI-specific backend logic is required.

## Start and access

1. Start one node or a Docker cluster (see project [README](../README.md)).
2. Open one node dashboard URL in browser (for example `http://localhost:10000/ui`).
3. Optional: change `API Base URL` in UI if you want to point to a different node endpoint.

## Component responsibilities

- `index.html`
  - Declares the dashboard sections (metrics strip, topology graph, node inspector, sensor table, event timeline).
  - Keeps rendering host containers only (no data logic).
- `app.js`
  - Polls `/api/introspection` at configurable intervals.
  - Normalizes introspection payloads and computes derived observability views.
  - Renders component sections:
    - topology graph (canvas, adaptive link rendering for larger `n`)
    - selected-node inspector
    - replicated sensor table (origin/timestamp/seq-version if present)
    - priority-first event timeline
    - metrics summary strip
- `styles.css`
  - Responsive, readable layout for desktop/mobile.
  - Visual status system for node health and event priority.

## Layout/readability strategy for larger clusters

- Topology rendering uses adaptive node placement by cluster size:
  - small clusters: radial
  - medium clusters: multi-ring
  - large clusters: compact grid
- Link rendering is capped for very dense graphs and prioritizes links that touch the local/selected node.
- Labels are reduced as node count grows; selected/local nodes remain labeled.
- Tables/timeline use scroll containers with row caps to prevent full-page degradation.

## Architectural boundary

- Frontend is static and read-only.
- Data source is introspection API contract only (`introspection/v1`).
- UI assets are served by `webapi` on the node Web API port for simpler deployment.
