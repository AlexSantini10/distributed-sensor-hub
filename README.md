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
- [Testing](#testing)
  - [Local test suite](#local-test-suite)
  - [Integration and Docker checks](#integration-and-docker-checks)
  - [Timed crash/recovery with Docker Compose](#timed-crashrecovery-with-docker-compose)
  - [Simulating latency and unstable networks](#simulating-latency-and-unstable-networks)
- [Notes](#notes)

## Documentation map

- [Architecture, technologies, and design choices](docs/architecture.md)
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
3. Replication updates are published to known peers.
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
| `PHI_THRESHOLD_SUSPECT` | Phi threshold for `suspected` status | `2.5` |
| `PHI_THRESHOLD_DEAD` | Phi threshold for `dead` status | `6.0` |
| `PHI_INITIAL_INTERVAL_S` | Baseline expected heartbeat interval (seconds) | `1.0` |
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
```

Stop a topology with the matching `docker compose ... down` command.

### Web API

```bash
curl http://localhost:10000/api/state
curl http://localhost:10000/api/updates
```

## Testing

### Local test suite

```bash
pytest --maxfail=1
pytest -v --maxfail=1
pytest -m protocol
python -m pytest tests/state/test_lww.py -q
```

Available pytest markers are defined in [pytest.ini](pytest.ini):

- `protocol`
- `networking`
- `membership`
- `gossip`
- `fd`
- `runtime`
- `state`
- `sensors`
- `webapi`
- `utils`
- `integration`

### Integration and Docker checks

```bash
docker compose -f docker/docker-compose-base.yml up --build -d
python tests/integration/verify_cluster.py --timeout 60 --interval 2
docker compose -f docker/docker-compose-base.yml down
```

### Timed crash/recovery with Docker Compose

You can simulate periodic node failures with:

Prerequisite: start this compose stack first:
`docker compose -f docker/docker-compose-6-nodes.yml up --build -d`.
The script only performs `docker compose stop/start` on an existing service.

```bash
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node3 \
  --down-seconds 20 \
  --up-seconds 40 \
  --cycles 5
```

PowerShell equivalent:

```powershell
python manual_tests/compose_chaos.py --compose-file docker/docker-compose-6-nodes.yml --service node3 --down-seconds 20 --up-seconds 40 --cycles 5
```

```powershell
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-6-nodes.yml `
  --service node3 `
  --down-seconds 20 `
  --up-seconds 40 `
  --cycles 5
```

Notes:
- `--service` is the Compose service name (`node1`, `node2`, ...), not `container_name`.
- Use `--cycles 0` for an infinite loop.
- Add `--initial-delay-seconds N` to wait before the first stop.

### Simulating latency and unstable networks

For phi-accrual and resilience tests, you can combine sensor and network simulation:

- Sensor latency: `SENSOR_<i>_LATENCY_MS`, `SENSOR_<i>_LATENCY_JITTER_MS`
- Network delay/loss: `NETWORK_DELAY_MS`, `NETWORK_DELAY_JITTER_MS`, `NETWORK_DELAY_SPIKE_PROB`, `NETWORK_DELAY_SPIKE_MS`, `NETWORK_PACKET_LOSS_PROB`

Example:

```bash
export NETWORK_DELAY_MS=40 NETWORK_DELAY_JITTER_MS=30
export NETWORK_DELAY_SPIKE_PROB=0.1 NETWORK_DELAY_SPIKE_MS=250
export NETWORK_PACKET_LOSS_PROB=0.02
export SENSOR_0_LATENCY_MS=60 SENSOR_0_LATENCY_JITTER_MS=40
```

Quick test flow:

```bash
# 1) Start the cluster
docker compose -f docker/docker-compose-6-nodes.yml up --build -d

# 2) Run chaos on one node (example: node3)
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node3 \
  --down-seconds 20 \
  --up-seconds 40 \
  --cycles 5

# 3) While chaos is running, inspect node state
curl http://localhost:10000/api/state
curl http://localhost:10001/api/state
curl http://localhost:10002/api/state

# 4) Optional convergence check
python tests/integration/verify_cluster.py --timeout 120 --interval 2

# 5) Cleanup
docker compose -f docker/docker-compose-6-nodes.yml down
```

CI workflows live in:

- [.github/workflows/pytest.yml](.github/workflows/pytest.yml)
- [.github/workflows/integration-tests.yml](.github/workflows/integration-tests.yml)

## Notes

- Logs are written to the path configured by `LOG_FILE`.
- The Docker setups mount logs into the repository `logs/` directory.
- The project license is available in [LICENSE](LICENSE).
