# Distributed Sensor Hub

> **Course:** Distributed Systems - MSc in Computer Science and Engineering
> **Institution:** University of Bologna (UNIBO)
> **Academic Year:** 2025/2026

Distributed Sensor Hub is a peer-to-peer system for aggregating heterogeneous IoT sensor data across a dynamic cluster of nodes. Each node generates sensor readings, replicates local state to known peers, and exposes an HTTP API for observing the merged cluster state.

## Authors

| Name | GitHub |
|------|--------|
| Alex Santini | [@AlexSantini10](https://github.com/AlexSantini10) |

## Documentation map

- [Architecture, technologies, and design choices](docs/architecture.md)
- [Roadmap and missing pieces](docs/roadmap.md)

## Project structure

| Path | Purpose |
|------|---------|
| `node.py` | Entry point for a node process |
| `runtime/` | Runtime orchestration and subsystem bootstrap |
| `state/` | LWW state worker and outbound update publishing |
| `membership/` | Peer model, peer table, and membership handlers |
| `protocol/` | Message envelope, message types, dispatcher, and protocol handlers |
| `networking/` | TCP client/server transport layer |
| `sensors/` | Sensor simulators and sensor manager |
| `webapi/` | HTTP API serving state and update snapshots |
| `docker/` | Dockerfiles and compose topologies |
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
| `SENSORS` | Number of sensors configured for the node | `4` |

See [.env.example](.env.example) for the full sensor-specific variables.

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
- `state`
- `sensors`

### Integration and Docker checks

```bash
docker compose -f docker/docker-compose-base.yml up --build -d
python tests/integration/verify_cluster.py --timeout 60 --interval 2
docker compose -f docker/docker-compose-base.yml down
```

CI workflows live in:

- [.github/workflows/pytest.yml](.github/workflows/pytest.yml)
- [.github/workflows/integration-tests.yml](.github/workflows/integration-tests.yml)

## Notes

- Logs are written to the path configured by `LOG_FILE`.
- The Docker setups mount logs into the repository `logs/` directory.
- The project license is available in [LICENSE](LICENSE).
