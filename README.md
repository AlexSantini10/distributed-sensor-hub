# Distributed Sensor Hub

> **Course:** Distributed Systems — MSc in Computer Science and Engineering  
> **Institution:** University of Bologna (UNIBO)  
> **Academic Year:** 2025/2026

---

## Table of Contents

1. [Course Context](#1-course-context)
2. [Authors](#2-authors)
3. [Abstract](#3-abstract)
4. [System Architecture](#4-system-architecture)
5. [Technologies Used](#5-technologies-used)
6. [Design Choices](#6-design-choices)
7. [Distributed Systems Concepts Applied](#7-distributed-systems-concepts-applied)
8. [Setup and Installation](#8-setup-and-installation)
9. [Usage Instructions](#9-usage-instructions)
10. [Experimental Evaluation](#10-experimental-evaluation)
11. [Limitations](#11-limitations)
12. [Future Work](#12-future-work)
13. [References](#13-references)

---

## 1. Course Context

This project was developed as a deliverable for the **Distributed Systems** course of the **MSc programme in Engineering and Computer Science** at the **University of Bologna (UNIBO)**. The objective is to design and implement a functional distributed system that applies core distributed-systems principles — including peer-to-peer communication, decentralised state replication, gossip-based membership management, and fault-tolerant networking — within a realistic IoT sensor aggregation scenario.

---

## 2. Authors

| Name | GitHub |
|------|--------|
| Alex Santini | [@AlexSantini10](https://github.com/AlexSantini10) |

---

## 3. Abstract

**Distributed Sensor Hub** is a peer-to-peer distributed system for aggregating heterogeneous IoT sensor data across a dynamic cluster of nodes. Each node independently generates sensor readings (temperature, humidity, motion, vibration, air quality, etc.), replicates its local state to all known peers, and maintains a globally consistent merged view of all sensor readings. The system is designed to operate without a central coordinator: cluster membership is discovered via a gossip-based JOIN/PEER_LIST exchange, and state replication uses a **Last-Write-Wins (LWW) CRDT** to guarantee conflict-free convergence under concurrent updates. Each node additionally exposes a REST HTTP API that allows clients to query the current global state and a stream of recent updates. The implementation targets containerised deployment via Docker, enabling reproducible multi-node experiments.

---

## 4. System Architecture

### 4.1 High-Level Overview

The system consists of a set of independent nodes, each running identically configured software. Nodes discover peers at start-up through a small set of pre-configured bootstrap addresses; subsequent membership propagation achieves eventual full connectivity via gossip.

```
┌───────────────────────────────────────────────────────────┐
│                         Node                              │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │  Sensors    │  │ State Worker │  │   Web API       │  │
│  │  (8 types)  │─▶│ (LWW CRDT)  │─▶│ GET /api/state  │  │
│  └─────────────┘  └──────┬───────┘  └─────────────────┘  │
│                          │                                │
│  ┌─────────────┐  ┌──────▼───────┐  ┌─────────────────┐  │
│  │ Membership  │  │   Update     │  │   TCP Client    │  │
│  │ (Peer Table)│  │  Publisher   │─▶│ (outbound P2P)  │  │
│  └─────────────┘  └──────────────┘  └─────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │       TCP Server (inbound) → Dispatcher             │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 4.2 Subsystems

#### Sensor Subsystem (`sensors/`)

Sensors are modelled as periodic daemon threads that emit readings to a shared event queue. Eight sensor types are supported:

| Type | Description | Example use |
|------|-------------|-------------|
| `NumericSensor` | Uniform random value in a configurable range | Temperature |
| `BooleanSensor` | Probabilistic true/false with configurable bias | Motion detection |
| `NoiseSensor` | Base value with additive Gaussian noise | Humidity |
| `WaveSensor` | Sinusoidal oscillation | Vibration |
| `TrendSensor` | Linear drift with superimposed noise | Air quality index |
| `SpikeSensor` | Baseline with low-probability impulse spikes | Traffic intensity |
| `CategoricalSensor` | Uniform random selection from a discrete label set | Alert categories |
| `IncrementalSensor` | Monotonically increasing counter | Event counts |

`SensorManager` loads sensor configuration entirely from environment variables and forwards each reading to the `NodeStateWorker` via a `Queue`.

#### State Replication (`state/`)

`NodeStateWorker` maintains the global merged sensor state in memory using LWW (Last-Write-Wins) semantics. The state key is `{origin_node_id}:{sensor_id}`, which eliminates cross-node key conflicts by design. Concurrent writes are resolved deterministically: the entry with the higher millisecond timestamp wins; ties are broken by lexical comparison of the originating node identifier. The worker exposes two independent read streams: a snapshot for the Web API and a replication queue consumed by `SensorUpdatePublisher`.

`SensorUpdatePublisher` polls the replication queue at a configurable interval (default: 200 ms) and broadcasts `SENSOR_UPDATE` messages to all known peers via the TCP client.

#### Membership (`membership/`)

`PeerTable` is a thread-safe registry mapping `node_id → Peer`. `Peer` records store the node address, last-seen heartbeat timestamp, a phi accrual failure score, and a status field (`alive` / `suspected` / `dead`).

Membership converges through gossip: upon receiving a `JOIN_REQUEST`, a node replies with its full `PEER_LIST`. The recipient processes any previously unknown entries, wires them into the TCP client, and immediately sends them a `JOIN_REQUEST` in turn. This mechanism achieves transitive closure across the cluster without a centralised directory.

#### Protocol & Message Handling (`protocol/`)

All inter-node communication uses a uniform `Message` envelope:

```
Message {
    msg_type  : MessageType   (enum)
    sender_id : str
    payload   : dict
    timestamp : int           (milliseconds since epoch, auto-assigned)
}
```

Messages are serialised to JSON, encoded as UTF-8, and framed over TCP with a 4-byte big-endian length prefix. `MessageDispatcher` provides a registry-based routing table mapping each `MessageType` to a dedicated handler.

Defined message types:

| Category | Types |
|----------|-------|
| Membership | `JOIN_REQUEST`, `PEER_LIST` |
| Heartbeat | `PING`, `PONG` |
| Replication | `SENSOR_UPDATE`, `GOSSIP_STATE` |
| Sync | `FULL_SYNC_REQUEST`, `FULL_SYNC_RESPONSE` |
| Control | `ACK`, `ERROR` |

#### Networking (`networking/`)

**`TcpServer`** accepts inbound connections on a configurable port. Each connection is handled in a dedicated thread; messages are read using the length-prefix framing protocol and dispatched to registered handlers.

**`TcpClient`** maintains one persistent outbound connection per peer. Sends are enqueued in a per-peer FIFO queue served by a dedicated worker thread. Reconnection uses exponential backoff (initial: 0.5 s, maximum: 10 s). TCP keepalive is enabled to detect silently dead peers.

#### Web API (`webapi/`)

A lightweight `ThreadingHTTPServer` exposes two endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/state` | Full LWW state snapshot (all nodes, all sensors) |
| `GET` | `/api/updates` | Incremental updates since last read (cleared on read) |

CORS is enabled with a wildcard origin to support browser-based dashboards.

### 4.3 Deployment Topology

The `docker/` directory provides two reference topologies:

- **`docker-compose-base.yml`** — 2-node cluster (nodes 1–2, ports 9000–9001 / 10000–10001).
- **`docker-compose-6-nodes.yml`** — 6-node ring cluster (nodes 1–6, ports 9000–9005 / 10000–10005) simulating an urban sensor network (downtown, industrial, residential districts).

```
docker-compose-base.yml

  ┌─────────┐          ┌─────────┐
  │ node-1  │◄────────►│ node-2  │
  │ :9000   │          │ :9001   │
  │ :10000  │          │ :10001  │
  └─────────┘          └─────────┘
```

```
docker-compose-6-nodes.yml

  node-1 ──► node-2 ──► node-3 ──┐
    ▲                             │
    └──── node-6 ◄── node-5 ◄── node-4
  (bootstrap peers form a directed ring; gossip achieves full mesh)
```

---

## 5. Technologies Used

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.14 | Implementation language |
| `python-dotenv` | ≥ 1.0 | Environment-based configuration |
| `pytest` | ≥ 9.0 | Unit and integration testing |
| Docker / Docker Compose | — | Containerised multi-node deployment |
| TCP sockets (`socket`) | stdlib | Inter-node transport layer |
| `threading` / `queue` | stdlib | Concurrency primitives |
| `http.server` | stdlib | REST API server |

No third-party web framework is used; all network logic is built directly on Python's standard library to maintain full visibility over the communication stack.

---

## 6. Design Choices

### No centralised coordinator

Every node is architecturally identical and autonomous. There is no master, leader, or broker. Membership and state are both maintained and replicated in a fully decentralised manner, which eliminates single points of failure from the core data path.

### LWW CRDT for state replication

Rather than employing a consensus protocol (e.g., Raft or Paxos), the system uses a Last-Write-Wins Conflict-free Replicated Data Type. This choice prioritises availability and partition tolerance (per the CAP theorem) over strong consistency. LWW is semantically appropriate for sensor telemetry, where the latest reading is always the most useful and stale data may be safely overwritten.

### Origin-scoped state keys

The composite key `{origin}:{sensor_id}` ensures that only the originating node writes to its own portion of the shared state. This design property eliminates write conflicts between nodes for different sensors, confining LWW conflict resolution to the case where the same node's update arrives via multiple gossip paths.

### Environment-variable configuration

All node parameters (identity, port, bootstrap peers, sensor definitions) are injected via environment variables. This enables the same Docker image to be instantiated as any node in the cluster by varying only the environment, which is consistent with twelve-factor app methodology and simplifies orchestration.

### Two independent update streams

The state worker maintains separate queues for the Web API (snapshot, cleared on read) and for replication (gossip broadcast). This separation prevents API polling from interfering with replication throughput and allows both consumers to have independent read semantics.

### TCP with length-prefix framing

A 4-byte big-endian length header precedes every message, providing reliable message boundary detection without relying on application-level delimiters. This is a standard approach for binary protocols over stream-oriented TCP and avoids the ambiguity of newline-delimited JSON for payloads that may themselves contain newlines.

---

## 7. Distributed Systems Concepts Applied

| Concept | Implementation |
|---------|----------------|
| **Gossip / Epidemic Protocol** | JOIN_REQUEST / PEER_LIST exchange for membership convergence |
| **CRDT (LWW Register)** | Conflict-free state merge in `NodeStateWorker` |
| **Eventual Consistency** | Sensor state converges across all nodes without coordination |
| **Failure Detection** | Phi-accrual metric infrastructure in `Peer`; heartbeat fields tracked |
| **Peer-to-Peer Communication** | Symmetric TCP connections; no hierarchy |
| **Decentralised Membership** | Peer discovery via transitive gossip; no directory server |
| **Fault-Tolerant Networking** | Exponential backoff reconnection; TCP keepalive |
| **Replication** | SENSOR_UPDATE broadcast; GOSSIP_STATE (partial, see Limitations) |
| **State Partitioning** | Origin-scoped keys prevent cross-node write conflicts |
| **Multi-threaded Concurrency** | Explicit locks on shared state; per-peer send queues |

---

## 8. Setup and Installation

### Prerequisites

- Python 3.14 or later
- `pip`
- Docker and Docker Compose (for containerised deployment)

### Local Installation

```bash
# Clone the repository
git clone https://github.com/AlexSantini10/distributed-sensor-hub.git
cd distributed-sensor-hub

# Install dependencies
pip install -r requirements.txt
```

### Running Tests

```bash
# Run the full test suite
pytest --maxfail=1

# Verbose output
pytest -v --maxfail=1

# Run a specific test module (markers: protocol, networking, membership, state, sensors)
pytest -m protocol

# Windows PowerShell
python -m pytest --maxfail=1
```

### Environment Configuration

Copy `.env.example` to `.env` and adjust as required:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `NODE_ID` | Unique node identifier | `node-1` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | TCP P2P port | `9000` |
| `BOOTSTRAP_PEERS` | Comma-separated `host:port` of seed peers | `node-2:9001` |
| `WEB_API_PORT` | HTTP API port (default: `PORT + 1000`) | `10000` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `LOG_FILE` | Path to log file | `/app/logs/node-1.log` |
| `SENSORS` | Number of sensors configured for this node | `4` |
| `SENSOR_N_TYPE` | Type of sensor N (e.g., `numeric`, `wave`, `spike`) | `numeric` |
| `SENSOR_N_NAME` | Sensor identifier | `temperature` |
| `SENSOR_N_PERIOD_MS` | Sampling interval in milliseconds | `1000` |

See `.env.example` for the complete list of per-sensor parameters.

---

## 9. Usage Instructions

### Single Node (Local)

```bash
export NODE_ID=node-1 HOST=0.0.0.0 PORT=9000 BOOTSTRAP_PEERS=""
export WEB_API_PORT=10000 LOG_LEVEL=INFO
export SENSORS=1 SENSOR_0_TYPE=numeric SENSOR_0_NAME=temperature \
       SENSOR_0_PERIOD_MS=1000 SENSOR_0_MIN=15 SENSOR_0_MAX=30 SENSOR_0_UNIT=C

python node.py
```

### Two-Node Cluster (Docker)

```bash
# Build and start both nodes
docker compose -f docker/docker-compose-base.yml up --build -d

# Follow logs
docker logs -f node-1
docker logs -f node-2

# Teardown
docker compose -f docker/docker-compose-base.yml down
```

### Six-Node Cluster (Docker)

```bash
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
```

### Querying the Web API

```bash
# Global sensor state (all nodes merged)
curl http://localhost:10000/api/state

# Incremental updates since last read
curl http://localhost:10000/api/updates
```

Example response for `/api/state`:

```json
{
  "node-1:temperature": {
    "value": 22.4,
    "unit": "C",
    "timestamp": 1714000000000,
    "origin": "node-1"
  },
  "node-2:pressure": {
    "value": 1013.2,
    "unit": "hPa",
    "timestamp": 1714000000120,
    "origin": "node-2"
  }
}
```

### Log Files

Log files are written to the path specified by `LOG_FILE`. In the Docker configurations, logs are mounted to a `logs/` volume in the repository root:

```bash
# Linux / macOS
cat logs/node-1.log

# Windows (PowerShell)
type logs\node-1.log
```

---

## 10. Experimental Evaluation

The system can be evaluated along the following dimensions using the provided Docker Compose configurations:

### State Convergence Latency

Deploy the 2- or 6-node cluster, query `/api/state` on one node immediately after a sensor update is emitted on another, and measure the time until the update appears. Given a replication interval of 200 ms and TCP connection latency of < 1 ms (loopback), convergence is expected within one replication cycle under normal conditions.

### Membership Convergence

Start a cluster in which node A knows only node B, and node B knows only node C. Observe through the logs that all three nodes eventually acquire full peer knowledge through the transitive JOIN_REQUEST / PEER_LIST gossip mechanism.

### Fault Tolerance

Terminate one node container (`docker stop node-2`) and verify that the remaining nodes continue to generate and replicate sensor data among themselves. Restart the stopped node and verify that it re-integrates into the cluster and its state converges.

> **Note:** Quantitative throughput or latency benchmarks have not been systematically collected in the current implementation. Results will vary with host hardware and Docker networking configuration.

---

## 11. Limitations

- **Incomplete failure detection.** The phi-accrual failure detector infrastructure (phi score, `last_heartbeat`, status field in `Peer`) is present but not fully activated. The `PING`/`PONG` handlers are stubs; no heartbeat loop is currently started.

- **GOSSIP_STATE not implemented.** The handler for `GOSSIP_STATE` messages raises `NotImplementedError`. Full gossip-based anti-entropy state reconciliation (useful for state repair after partitions) is absent.

- **FULL_SYNC not implemented.** `FULL_SYNC_REQUEST` / `FULL_SYNC_RESPONSE` handlers are placeholders. New nodes joining an established cluster receive only updates emitted after their join; they do not recover historical state.

- **No cycle detection in gossip.** The gossip membership protocol does not implement a seen-set or TTL counter. In dense clusters, redundant messages may circulate; at low gossip frequency this is benign but would need addressing at scale.

- **No persistence.** All node state is held in memory. A process restart results in complete state loss; no write-ahead log or snapshot mechanism is provided.

- **No security.** Inter-node communication is unauthenticated and unencrypted. The system assumes a trusted private network.

- **Single bootstrap peer per node.** The `BOOTSTRAP_PEERS` variable accepts a comma-separated list, but each node is typically configured with a single seed peer in the provided Docker Compose files, which makes bootstrap resilience dependent on that peer's availability.

---

## 12. Future Work

- **Complete failure detection.** Implement the PING/PONG heartbeat loop and integrate the phi-accrual detector to transition peers through `alive → suspected → dead` states, triggering removal from the replication set.

- **Anti-entropy via GOSSIP_STATE.** Implement periodic full-state gossip rounds between random peer pairs to repair divergent state after network partitions or missed updates.

- **State persistence.** Add a write-ahead log or periodic snapshot to stable storage, enabling nodes to recover their state following a restart without requiring a full sync from peers.

- **FULL_SYNC on join.** Implement the `FULL_SYNC_REQUEST` / `FULL_SYNC_RESPONSE` protocol so that newly joined nodes can retrieve the complete current state from an existing peer before entering the replication stream.

- **Bounded gossip (cycle prevention).** Introduce a message ID with a seen-set or a hop-count TTL to prevent gossip messages from circulating indefinitely in larger, more densely connected clusters.

- **TLS and authentication.** Secure inter-node channels with mutual TLS and add a lightweight authentication mechanism to prevent unauthorised nodes from injecting state updates.

- **Dynamic topology.** Support runtime addition and removal of nodes, including graceful departure notifications (`LEAVE` message type) that allow peers to promptly evict the departing node from their peer tables.

- **Metrics and observability.** Integrate Prometheus-compatible metrics (replication lag, message throughput, peer count) and a Grafana dashboard for cluster-level monitoring.

---

## 13. References

1. Vogels, W., van Renesse, R., & Birman, K. (2003). *The power of epidemics: robust communication for large-scale distributed systems*. ACM SIGCOMM Computer Communication Review, 33(1), 131–135.

2. Shapiro, M., Preguiça, N., Baquero, C., & Zawirski, M. (2011). *Conflict-free replicated data types*. Proceedings of the 13th International Symposium on Stabilization, Safety, and Security of Distributed Systems (SSS 2011), LNCS 6976, 386–400.

3. Hayashibara, N., Défago, X., Yared, R., & Katayama, T. (2004). *The φ accrual failure detector*. Proceedings of the 23rd IEEE International Symposium on Reliable Distributed Systems (SRDS 2004), 66–78.

4. Brewer, E. A. (2000). *Towards robust distributed systems* (keynote). Proceedings of the 19th Annual ACM Symposium on Principles of Distributed Computing (PODC 2000).

5. van Steen, M., & Tanenbaum, A. S. (2023). *Distributed Systems* (4th ed.). Maarten van Steen. Available at: https://www.distributed-systems.net

6. Demers, A., Greene, D., Hauser, C., Irish, W., Larson, J., Shenker, S., Sturgis, H., Swinehart, D., & Terry, D. (1987). *Epidemic algorithms for replicated database maintenance*. Proceedings of the 6th ACM Symposium on Principles of Distributed Computing (PODC 1987), 1–12.

---

*This project is released under the terms of the [LICENSE](LICENSE) file included in this repository.*
