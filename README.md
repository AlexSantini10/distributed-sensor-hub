# Distributed Sensor Hub

> **Course:** Distributed Systems - MSc in Computer Science and Engineering
> **Institution:** University of Bologna (UNIBO)
> **Academic Year:** 2025/2026

Distributed Sensor Hub is a peer-to-peer system for aggregating heterogeneous IoT sensor data across a dynamic cluster of nodes. Each node generates sensor readings, replicates local state to known peers, and exposes an HTTP API for observing the merged cluster state.

## Authors

| Name | GitHub |
|------|--------|
| Alex Santini | [@AlexSantini10](https://github.com/AlexSantini10) |

## Table of contents

- [Documentation map](#documentation-map)
- [Core capabilities](#core-capabilities)
- [How a node works](#how-a-node-works)
- [Project structure](#project-structure)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Local installation](#local-installation)
  - [Environment configuration](#environment-configuration)
- [Running the project](#running-the-project)
  - [Single node](#single-node)
  - [Docker topologies](#docker-topologies)
  - [Web API](#web-api)
- [Notes](#notes)

## Documentation map

- [Architecture, technologies, and design choices](docs/architecture.md)
- [Testing guide and Docker validation scenarios](docs/testing.md)
- [Roadmap and missing pieces](docs/roadmap.md)

Module documentation:

| Module | README |
|--------|--------|
| `fd/` | [Phi-accrual failure detection](fd/README.md) |
| `runtime/` | [Runtime orchestration and subsystem bootstrap](runtime/README.md) |

## Core capabilities

- Peer-to-peer node architecture with no centralized coordinator
- Configuration-driven sensor simulation with multiple built-in providers
- Last-Write-Wins replicated state convergence across nodes
- Membership discovery through bootstrap peers and peer-list exchange
- Phi-accrual-based liveness metadata for peer health tracking
- HTTP endpoints for cluster state and incremental update inspection
- Docker topologies and automated tests for local validation

## How a node works

At startup, a node loads environment-based configuration, initializes logging, starts the local state worker, brings up TCP networking, contacts bootstrap peers, starts heartbeats, launches sensor producers, and finally exposes the Web API.

The steady-state data flow is:

1. Local sensors emit readings into the shared event queue.
2. The state worker normalizes events and applies LWW merges.
3. Replication updates run in push-pull rounds with scalable fanout over alive peers.
4. Remote messages are dispatched by protocol handlers and merged locally.
5. The Web API exposes full state and incremental updates for inspection.

## Project structure

| Path | Purpose |
|------|---------|
| `node.py` | Entry point for a node process |
| `docs/` | Architecture notes and technical documentation |
| `runtime/` | [Runtime orchestration and subsystem bootstrap](runtime/README.md) |
| `fd/` | [Phi-accrual failure detection](fd/README.md) |
| `state/` | LWW state worker and outbound update publishing |
| `membership/` | Peer model, peer table, and membership handlers |
| `protocol/` | Message envelope, message types, dispatcher, and protocol handlers |
| `networking/` | TCP client/server transport layer |
| `sensors/` | Sensor simulators and sensor manager |
| `webapi/` | HTTP API serving state and update snapshots |
| `web/` | Static UI assets for monitoring |
| `docker/` | Dockerfiles and compose topologies |
| `manual_tests/` | Helper scripts for manual resilience experiments |
| `tests/` | Unit and integration tests |
| `.github/workflows/` | CI workflows for pytest and integration checks |

## Setup

### Prerequisites

- Python 3.14 or later
- `pip`
- Docker and Docker Compose

### Local installation

```bash
git clone https://github.com/AlexSantini10/distributed-sensor-hub.git
cd distributed-sensor-hub
pip install -r requirements.txt
```

### Environment configuration

Use [.env.example](.env.example) as the base configuration.

| Variable | Description | Example |
|----------|-------------|---------|
| `NODE_ID` | Unique node identifier | `node-1` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | TCP P2P port | `9000` |
| `BOOTSTRAP_PEERS` | Comma-separated `host:port` seed peers | `node-2:9001` |
| `WEB_API_PORT` | HTTP API port | `10000` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `LOG_FILE` | Node log path | `/app/logs/node-1.log` |
| `PHI_THRESHOLD_SUSPECT` | Phi threshold for `suspected` status | `3.0` |
| `PHI_THRESHOLD_DEAD` | Phi threshold for `dead` status | `8.0` |
| `PHI_INITIAL_INTERVAL_S` | Baseline expected heartbeat interval (seconds) | `1.0` |
| `GOSSIP_SYNC_INTERVAL_MS` | Push-pull replication round interval (ms) | `1000` |
| `GOSSIP_PUSH_RATIO` | Push fanout ratio over alive peers (`0..1`) | `0.3` |
| `GOSSIP_PUSH_MIN_PEERS` | Minimum push fanout per round | `2` |
| `GOSSIP_PULL_RATIO` | Pull fanout ratio over alive peers (`0..1`) | `0.15` |
| `GOSSIP_PULL_MIN_PEERS` | Minimum pull fanout when pull runs | `1` |
| `GOSSIP_PULL_EVERY_ROUNDS` | Run one pull round every N push rounds | `3` |
| `SENSORS` | Number of sensors configured for the node | `4` |
| `NETWORK_DELAY_MS` | Base artificial outbound network delay (ms) | `35` |
| `NETWORK_DELAY_JITTER_MS` | Random delay jitter radius (ms) | `25` |
| `NETWORK_DELAY_SPIKE_PROB` | Probability of delay spike per message (`0..1`) | `0.08` |
| `NETWORK_DELAY_SPIKE_MS` | Extra delay when a spike occurs (ms) | `220` |
| `NETWORK_PACKET_LOSS_PROB` | Probability of dropping outbound message (`0..1`) | `0.01` |

See [.env.example](.env.example) for the full sensor-specific variables.
Each sensor can also define `SENSOR_<i>_LATENCY_MS` and `SENSOR_<i>_LATENCY_JITTER_MS`.

## Running the project

### Single node

PowerShell:

```powershell
$env:NODE_ID="node-1"
$env:HOST="0.0.0.0"
$env:PORT="9000"
$env:BOOTSTRAP_PEERS=""
$env:WEB_API_PORT="10000"
$env:LOG_LEVEL="INFO"
$env:SENSORS="1"
$env:SENSOR_0_TYPE="numeric"
$env:SENSOR_0_NAME="temperature"
$env:SENSOR_0_PERIOD_MS="1000"
$env:SENSOR_0_MIN="15"
$env:SENSOR_0_MAX="30"
$env:SENSOR_0_UNIT="C"
python node.py
```

Linux/macOS:

```bash
export NODE_ID=node-1 HOST=0.0.0.0 PORT=9000 BOOTSTRAP_PEERS=""
export WEB_API_PORT=10000 LOG_LEVEL=INFO
export SENSORS=1 SENSOR_0_TYPE=numeric SENSOR_0_NAME=temperature \
       SENSOR_0_PERIOD_MS=1000 SENSOR_0_MIN=15 SENSOR_0_MAX=30 SENSOR_0_UNIT=C
python node.py
```

### Docker topologies

```bash
docker compose -f docker/docker-compose-base.yml up --build -d
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
```

Stop a topology with the matching `docker compose ... down` command.

### Web API

Per monitorare il cluster si usa normalmente la UI statica in [web/index.html](web/index.html), che interroga gli endpoint HTTP esposti dai nodi.

## Testing

Testing workflows, deterministic state convergence checks, Docker validation scenarios, and chaos experiments live in [docs/testing.md](docs/testing.md).

## Notes

- Logs are written to the path configured by `LOG_FILE`.
- The Docker setups mount logs into the repository `logs/` directory.
- The project license is available in [LICENSE](LICENSE).
