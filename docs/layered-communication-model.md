# Layered Communication Model

This note summarizes the high-level layering used in the project.

## Three Levels

1. `networking` (TCP transport)
- Owns socket-level communication.
- Handles connection lifecycle, framing, retries/backoff, and inbound/outbound I/O.

2. `protocol` (message contract and routing)
- Defines message types and payload schemas.
- Encodes/decodes messages and dispatches each inbound message to the correct handler by `MessageType`.

3. Domain modules (business semantics)
- Modules such as `membership`, `gossip`, `state`, `topology`, and related runtime callbacks.
- Apply real state transitions and domain-side effects after protocol dispatch.

## End-to-End Path (Inter-Node)

For node-to-node traffic, the path is:

`domain intent -> protocol message build -> networking TCP send -> networking TCP receive -> protocol decode/dispatch -> domain handler logic`

This is the core path for cluster communication.

## Important Scope Note

Not every runtime flow crosses all three levels.

- Local in-process flows (for example `sensors -> state worker`) can bypass `protocol` and `networking`.
- Read-only observability flows (`introspection`, `webapi`) are local/HTTP-facing and not part of peer-to-peer protocol routing.

