# webapi

## Purpose

The `webapi` module exposes a **read-only HTTP observation interface** for node-local replicated data.
Its system role is to bridge internal state/membership workers and external polling clients (e.g., dashboards, tests) without participating in replication or conflict resolution.

## File Overview

- `webapi/http_api.py`: Implements request routing, JSON serialization of provided snapshots, permissive CORS handling for polling clients, and lifecycle management of a threaded HTTP server.

## Main Dependencies

- `http.server` (stdlib): Provides `BaseHTTPRequestHandler` and `ThreadingHTTPServer` for concurrent TCP request serving.
- `threading` (stdlib): Hosts the HTTP server in a dedicated daemon thread (`WebAPIServer`).
- `json` (stdlib): Serializes snapshot objects into wire payloads.
- `protocol.contracts`: Supplies canonical HTTP content-type and UTF-8 encoding constants used in responses.
- `utils.typing`: Defines provider/logger structural types used for dependency injection (`SnapshotProvider`, `MembershipSnapshotProvider`, `TopologySnapshotProvider`, `LoggerLike`).
- `state`, `membership`, and `topology` (internal providers via runtime wiring): Supply full-state, incremental-update, optional membership, and optional topology snapshots consumed by this module.

## High-Level Design

- **Core responsibilities**:
  - Serve current snapshots of replicated node state and incremental updates.
  - Optionally serve membership snapshots when a membership provider is configured.
  - Optionally serve merged topology snapshots when a topology provider is configured.
  - Enforce a constrained HTTP surface (`GET`, `OPTIONS`) with CORS headers for browser-based polling.
  - Isolate HTTP failures from domain workers through exception handling and logger-based reporting.

- Main data flow:
  - Runtime injects zero-argument snapshot provider callables into a configured request handler.
  - For each accepted request, the handler selects the endpoint, invokes the corresponding provider, serializes the returned snapshot to JSON/UTF-8, and writes the HTTP response.
  - If provider execution or serialization fails, the handler returns `500`; unknown routes return `404`; `OPTIONS` returns preflight metadata (`204`).

- Interactions with other modules:
  - With `runtime.startup` (or equivalent composition layer): receives injected providers and bind configuration.
  - With `state`: reads full-state and incremental-update views produced by the state worker/store.
  - With `membership`: reads Phi-based membership view when membership integration is enabled.
  - With external clients (`web` UI/tests): provides a polling endpoint layer only; it does not mutate replicated state.
