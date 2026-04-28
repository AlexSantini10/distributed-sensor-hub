# Distributed Sensor Hub

Peer-to-peer system for distributed IoT sensor simulation and replicated state convergence.
Each node runs sensors, state merge, membership/liveness, TCP protocol handling, and a read-only HTTP API.

> **Course:** Distributed Systems - MSc in Computer Science and Engineering  
> **Institution:** University of Bologna (UNIBO)  
> **Academic Year:** 2025/2026
>
> **Course Report:** [Distributed Sensor Hub Final Report (PDF)](docs/report/distributed-sensor-hub-final-report.pdf)

## Quick links

- [Docs index](docs/README.md)
- [Docker CD](docs/docker-cd.md)
- [Course report (PDF)](docs/report/distributed-sensor-hub-final-report.pdf)
- [Course report repository (LaTeX source)](https://github.com/AlexSantini10/distributed-sensor-hub-report)
- [Architecture](docs/architecture.md)
- [Node services inventory](docs/node-services.md)
- [Testing](docs/testing.md)
- [Introspection API](docs/introspection-api.md)
- [Observability UI](web/README.md)

## Module map

| Module | Responsibility | README |
|---|---|---|
| `runtime/` | Startup, wiring, lifecycle | [runtime/README.md](runtime/README.md) |
| `protocol/` | Message contracts, codec, dispatcher, handlers | [protocol/README.md](protocol/README.md) |
| `networking/` | TCP client/server and framing | [networking/README.md](networking/README.md) |
| `membership/` | Peer table, liveness metadata, membership merge | [membership/README.md](membership/README.md) |
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
6. Web API exposes snapshots (`/api/state`, `/api/updates`, `/api/membership`, `/api/introspection`).

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
- Inbound TCP resilience:
  - `SOCKET_TIMEOUT` (socket read/accept timeout in seconds)
  - `ACCEPT_QUEUE_SIZE` (listen backlog)
  - `MAX_CONNECTIONS` (max concurrent active inbound connections)
  - `MAX_WORKERS` (max concurrent inbound handler workers)
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

Observability UI:

- Open the node dashboard URL directly, for example `http://localhost:10000/ui`.
- The same port serves both the dashboard static assets (`/`, `/index.html`, `/app.js`, `/styles.css`) and API endpoints (`/api/*`).
- In multi-node Docker runs, open any node dashboard URL you want to observe (for example `http://localhost:10003/ui`).

## Replication tuning (avoid saturation)

When many nodes and sensors are active, stale data in UI is usually caused by pull storms and/or a too-small delta history.

Recommended baseline for `docker-compose-6-nodes.yml`, `docker-compose-12-nodes.yml`, and `docker-compose-base.yml`:

- `GOSSIP_SYNC_INTERVAL_MS: 1000`
- `GOSSIP_PUSH_RATIO: 0.35`
- `GOSSIP_PUSH_MIN_PEERS: 1`
- `GOSSIP_PULL_RATIO: 0.05`
- `GOSSIP_PULL_MIN_PEERS: 1`
- `GOSSIP_PULL_EVERY_ROUNDS: 6`
- `REPLICATION_DELTA_MAXLEN: 4096`

Sensor cadence for demos (mixed load, clearer UI behavior):

- Keep a few "fast" sensors at `1200-2500 ms`.
- Keep non-critical sensors at `10000-15000 ms`.
- Avoid making all sensors fast at the same time.

Practical rule of thumb:

- If you increase fast sensors, first increase `REPLICATION_DELTA_MAXLEN`.
- Increase pull pressure only if freshness is low and push alone is not enough.
- Keep pull less aggressive than push in stable networks.

Symptoms and actions:

- Many `sensor_update_received` with `applied:false` and `source:"pull"`: reduce `GOSSIP_PULL_RATIO` and/or increase `GOSSIP_PULL_EVERY_ROUNDS`.
- Frequent `DELTA_UNAVAILABLE` or very old UI timestamps: increase `REPLICATION_DELTA_MAXLEN`.
- CPU/network pressure too high: increase `GOSSIP_SYNC_INTERVAL_MS` (for example `1200-1500`) and slow non-critical sensors.

Suggested safe ranges:

- `GOSSIP_SYNC_INTERVAL_MS`: `800-1500`
- `GOSSIP_PUSH_RATIO`: `0.25-0.5`
- `GOSSIP_PULL_RATIO`: `0.05-0.25`
- `GOSSIP_PULL_EVERY_ROUNDS`: `3-8`
- `REPLICATION_DELTA_MAXLEN`: `2048-8192`

Validation checklist after tuning:

1. Restart compose and wait at least 1-2 minutes.
2. Check introspection counters: `get_delta_unavailable_total` should stay near `0`.
3. Verify retained delta buffer is not constantly full.
4. In UI, most sensor timestamps should be recent (seconds, not minutes) for "fast" sensors.
5. `applied:false` events can exist, but they should not dominate traffic for long periods.

## Validation

- Unit + integration overview: [docs/testing.md](docs/testing.md)
- Quick local run: `pytest --maxfail=1`

## Docker CD

GitHub Actions builds the node container image from `docker/Dockerfile.base` on every push to `main` and publishes the rolling tags on `ghcr.io/<owner>/<repo>`.

When you push a version tag such as `v1.0.0`, the workflow also creates the GitHub Release for that commit and attaches a small usage bundle with instructions, a `.env` example, and a minimal Compose file pinned to the released image digest. Pull requests to `main` still validate that the image builds, but they do not publish artifacts. Full usage details are documented in [docs/docker-cd.md](docs/docker-cd.md).

## Notes

- Logs follow `LOG_FILE` and are mounted to `logs/` in Docker setups.
- Protocol `ERROR`/`ACK` handlers are currently placeholders in runtime setup.
- License: [LICENSE](LICENSE)
