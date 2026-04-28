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

- [runtime](../runtime/README.md)
- [protocol](../protocol/README.md)
- [networking](../networking/README.md)
- [membership](../membership/README.md)
- [fd](../fd/README.md)
- [gossip](../gossip/README.md)
- [state](../state/README.md)
- [sensors](../sensors/README.md)
- [topology](../topology/README.md)
- [introspection](../introspection/README.md)
- [webapi](../webapi/README.md)
- [web dashboard](../web/README.md)
