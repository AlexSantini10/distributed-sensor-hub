# Documentation

This directory contains project-level technical documentation.
Module-level details are documented in each module README.

## Project docs

- [Architecture](architecture.md)
- [Docker CD](docker-cd.md)
- [Layered Communication Model](layered-communication-model.md)
- [Node Services Inventory](node-services.md)
- [Testing](testing.md)
- [Introspection API](introspection-api.md)

## Dashboard URL

- The observability dashboard is served by each node on the Web API port at `/ui`.
- Example (single node): `http://localhost:10000/ui`
- Example (6 nodes): `http://localhost:10000/ui` ... `http://localhost:10005/ui`

## Module docs

- [runtime](../src/runtime/README.md)
- [protocol](../src/protocol/README.md)
- [networking](../src/networking/README.md)
- [membership](../src/membership/README.md)
- [fd](../src/fd/README.md)
- [gossip](../src/gossip/README.md)
- [state](../src/state/README.md)
- [sensors](../src/sensors/README.md)
- [topology](../src/topology/README.md)
- [introspection](../src/introspection/README.md)
- [webapi](../src/webapi/README.md)
- [web dashboard](../src/web/README.md)
- [utils](../src/utils/README.md)
