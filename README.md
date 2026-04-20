# Distributed Sensor Hub

Peer-to-peer system for distributed IoT sensor simulation and replicated state convergence.
Each node runs sensors, state merge, membership/liveness, TCP protocol handling, and a read-only HTTP API.

> **Course:** Distributed Systems - MSc in Computer Science and Engineering  
> **Institution:** University of Bologna (UNIBO)  
> **Academic Year:** 2025/2026

## Quick links

- [Docs index](docs/README.md)
- [Architecture](docs/architecture.md)
- [Testing](docs/testing.md)
- [Module dependencies diagram (PlantUML)](docs/module-dependencies.puml)

## Module map

| Module | Responsibility | README |
|---|---|---|
| `runtime/` | Startup, wiring, lifecycle | [runtime/README.md](runtime/README.md) |
| `protocol/` | Message contracts, codec, dispatcher, handlers | [protocol/README.md](protocol/README.md) |
| `networking/` | TCP client/server and framing | [networking/README.md](networking/README.md) |
| `membership/` | Peer table, liveness state, membership merge | [membership/README.md](membership/README.md) |
| `fd/` | Phi-accrual failure detection | [fd/README.md](fd/README.md) |
| `gossip/` | Membership dissemination (`GOSSIP_STATE`) | [gossip/README.md](gossip/README.md) |
| `state/` | Local authoritative state and LWW merge | [state/README.md](state/README.md) |
| `sensors/` | Sensor providers and ingestion boundary | [sensors/README.md](sensors/README.md) |
| `topology/` | Topology policy and peer selection | [topology/README.md](topology/README.md) |
| `webapi/` | Read-only HTTP observation API | [webapi/README.md](webapi/README.md) |

## System behavior

1. Sensors emit readings into the local event queue.
2. State worker applies **LWW** on `(ts_ms, origin)`.
3. Runtime runs periodic push/pull replication (`SENSOR_UPDATE`, `GET_DELTA`).
4. Protocol handlers merge inbound deltas/snapshots.
5. Membership is updated via `JOIN_REQUEST`, `PEER_LIST`, `PING/PONG`, `GOSSIP_STATE`.
6. Web API exposes snapshots (`/api/state`, `/api/updates`, `/api/membership`).

## Setup

Prerequisites:

- Python `3.14+`
- `pip`
- Docker + Docker Compose

Install:

```bash
git clone https://github.com/AlexSantini10/distributed-sensor-hub.git
cd distributed-sensor-hub
pip install -r requirements.txt
```

Base configuration:

- Start from [.env.example](.env.example).
- Required identifiers/bindings: `NODE_ID`, `HOST`, `PORT`, `WEB_API_PORT`.
- Cluster bootstrap: `BOOTSTRAP_PEERS`.
- Replication cadence/fanout: `GOSSIP_SYNC_INTERVAL_MS`, `GOSSIP_PUSH_*`, `GOSSIP_PULL_*`.
- Failure detection thresholds: `PHI_THRESHOLD_SUSPECT`, `PHI_THRESHOLD_DEAD`.

## Run

Single node (PowerShell):

```powershell
$env:NODE_ID="node-1"
$env:HOST="0.0.0.0"
$env:PORT="9000"
$env:BOOTSTRAP_PEERS=""
$env:WEB_API_PORT="10000"
python node.py
```

Docker topologies:

```bash
docker compose -f docker/docker-compose-base.yml up --build -d
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
```

## Validation

- Unit + integration overview: [docs/testing.md](docs/testing.md)
- Quick local run: `pytest --maxfail=1`

## Notes

- Logs follow `LOG_FILE` and are mounted to `logs/` in Docker setups.
- Protocol `ERROR`/`ACK` handlers are currently placeholders in runtime setup.
- License: [LICENSE](LICENSE)
