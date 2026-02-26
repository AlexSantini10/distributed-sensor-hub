# Distributed Sensor Hub

**Course:** Distributed Systems — MSc in Engineering and Computer Science  
**Institution:** University of Bologna (UNIBO)  
**Academic Year:** 2024/2025  
**Authors:** \[Author names — placeholder\]  
**License:** GNU General Public License v3.0

---

## Abstract

Distributed Sensor Hub is a peer-to-peer distributed system in which each node independently produces sensor readings and propagates them across the network to maintain a globally consistent view of all sensor data. The system is designed to operate without a central coordinator: any node may join or leave the cluster at any time, and state convergence is achieved through a Last-Write-Wins (LWW) Conflict-free Replicated Data Type (CRDT). A REST HTTP API exposed by each node allows external clients to query the current global sensor state or retrieve incremental updates. The project constitutes a practical exploration of the fundamental trade-offs described by the CAP theorem, demonstrating how an AP (Available, Partition-tolerant) system design achieves eventual consistency in the presence of concurrent writes and network partitions.

---

## Course Context

This project was developed as a deliverable for the **Distributed Systems** course of the MSc programme in **Engineering and Computer Science** at the **University of Bologna (UNIBO)**. The objective is to design and implement a realistic distributed application that demonstrates core concepts from the course, including decentralised architecture, peer-to-peer communication, membership management, consistency models, and fault tolerance.

---

## System Architecture

The system is composed of a set of homogeneous nodes that form a peer-to-peer mesh network. Each node runs the same software stack and participates symmetrically in both state production and state dissemination.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Node (node.py)                             │
│                                                                         │
│  ┌───────────────┐   sensor events   ┌───────────────────────────────┐  │
│  │ SensorManager │ ───────────────►  │   NodeStateWorker (LWW CRDT)  │  │
│  │  (8 types)    │                   │   _state: global sensor map   │  │
│  └───────────────┘                   └──────────┬────────────────────┘  │
│                                                 │ replication updates    │
│                                      ┌──────────▼─────────────────────┐ │
│                                      │  SensorUpdatePublisher         │ │
│                                      │  (200 ms broadcast interval)   │ │
│                                      └──────────┬─────────────────────┘ │
│                                                 │ SENSOR_UPDATE msgs     │
│  ┌──────────────────────────┐       ┌───────────▼──────────────────────┐│
│  │   TcpServer              │       │   TcpClient                      ││
│  │   (length-prefixed TCP)  │◄──────│   (length-prefixed TCP)          ││
│  └──────────────────────────┘       └──────────────────────────────────┘│
│            │ inbound msgs                                                │
│  ┌─────────▼────────────────┐       ┌──────────────────────────────────┐│
│  │   Protocol Dispatcher    │       │   WebAPIServer                   ││
│  │   (message routing)      │       │   GET /api/state                 ││
│  │   Membership handlers    │       │   GET /api/updates               ││
│  │   State merge handlers   │       └──────────────────────────────────┘│
│  └──────────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Module | Responsibility |
|-----------|--------|----------------|
| **Entry point** | `node.py` | Orchestrates subsystem lifecycle; manages graceful shutdown |
| **Sensor manager** | `sensors/sensor_manager.py` | Loads sensor definitions from environment; starts periodic sensor threads |
| **State worker** | `state/node_state_worker.py` | Processes sensor events; applies LWW merge; maintains two output buffers (UI, replication) |
| **Update publisher** | `state/sensor_update_publisher.py` | Drains the replication buffer every 200 ms; broadcasts `SENSOR_UPDATE` messages to all known peers |
| **TCP server** | `networking/tcp_server.py` | Multi-threaded TCP listener; decodes length-prefixed frames; dispatches to protocol handlers |
| **TCP client** | `networking/tcp_client.py` | Manages outbound persistent connections to peers; encodes length-prefixed frames |
| **Protocol dispatcher** | `protocol/dispatcher.py` | Routes inbound messages by `MessageType` to registered handlers |
| **Membership** | `membership/peer_table.py`, `membership/handlers.py` | Thread-safe registry of known peers; handles `JOIN_REQUEST` and `PEER_LIST` messages |
| **Web API** | `webapi/http_api.py` | Serves JSON state snapshots over HTTP via Python's `ThreadingHTTPServer` |
| **Configuration** | `utils/config.py` | Loads node identity, network parameters, and sensor definitions from environment variables |

---

## Technologies Used

| Category | Technology |
|----------|------------|
| **Language** | Python 3.14 |
| **Transport** | TCP sockets (Python `socket` / `socketserver` stdlib) |
| **HTTP server** | Python `http.server.ThreadingHTTPServer` (stdlib) |
| **Concurrency** | Python `threading` stdlib (thread-per-connection, daemon threads) |
| **Serialisation** | JSON (stdlib `json`) |
| **Configuration** | Environment variables, `python-dotenv` |
| **Containerisation** | Docker, Docker Compose |
| **Testing** | `pytest` |

No third-party networking or messaging framework is used; all transport and protocol logic is implemented directly on top of the Python standard library.

---

## Design Choices

### Length-prefixed TCP Framing

TCP is a stream-oriented protocol with no inherent message boundaries. Each message is prefixed with a 4-byte big-endian integer indicating the payload length. The receiver reads exactly that many bytes before decoding the JSON payload. This avoids the complexity of delimiter-based framing and handles arbitrary message sizes reliably.

### JSON Message Serialisation

All inter-node messages are serialised as JSON objects. Each `Message` object carries a `type` field (drawn from the `MessageType` enum), a `sender_id`, a Unix millisecond timestamp (`ts_ms`), and a `payload` dictionary whose schema is specific to the message type. JSON is chosen for its human readability during development and debugging; a binary encoding (e.g., MessagePack) could be substituted to reduce bandwidth.

### Last-Write-Wins CRDT

The distributed state is modelled as a `LWW-Map` (Last-Write-Wins Map). Each sensor reading is keyed by a *global sensor identifier* formed as `"<origin_node_id>:<sensor_id>"` to prevent collisions across nodes. The merge rule is:

1. If the incoming timestamp `ts_ms` is **strictly greater** than the stored timestamp, the update is applied.
2. If timestamps are **equal**, the update with the lexicographically **greater** `origin` field wins (deterministic tie-breaking).
3. Otherwise, the update is discarded as stale.

This ensures convergence without coordination: any order of applying updates from any set of peers will eventually yield the same state.

### Decoupled State Buffers

`NodeStateWorker` maintains two independent write-ahead buffers populated on every accepted update:

- **`_updates_ui`** — consumed by `GET /api/updates` (cleared on read; used for incremental polling).
- **`_updates_replication`** — consumed by `SensorUpdatePublisher` (cleared on read; drives outbound replication).

Separating the two buffers ensures that the replication pipeline and the HTTP API do not interfere with each other's read cursors.

### Thread-per-Connection Server

`TcpServer` spawns a new daemon thread for each accepted inbound connection. This is a straightforward concurrency model appropriate for a research prototype with a bounded number of peers. A production deployment could replace this with an event-loop (e.g., `asyncio`) to improve scalability.

### Bootstrap via `JOIN_REQUEST` / `PEER_LIST`

When a node starts, it sends a `JOIN_REQUEST` message to each statically configured bootstrap peer. The receiving node replies with a `PEER_LIST` message containing all peers currently in its membership table. This two-message handshake allows a joining node to discover the wider cluster topology after contacting only a single existing member.

---

## Distributed System Concepts Applied

| Concept | Implementation |
|---------|---------------|
| **Eventual consistency** | LWW-CRDT ensures all nodes converge to the same sensor state without synchronous coordination |
| **CRDT (Conflict-free Replicated Data Type)** | `NodeStateWorker.merge_update()` implements a LWW-Map with deterministic tie-breaking |
| **Peer-to-peer architecture** | All nodes are structurally identical; there is no designated leader or coordinator |
| **Membership management** | `PeerTable` tracks known peers with liveness metadata (`status`: `alive` / `suspected` / `dead`); `JOIN_REQUEST` / `PEER_LIST` exchange drives discovery |
| **Failure detection** | Each `Peer` dataclass carries a `phi` (accrual failure detector) field and a `last_heartbeat` timestamp, providing the infrastructure for Phi-accrual failure detection |
| **Gossip dissemination** | `GOSSIP_STATE` and `FULL_SYNC_REQUEST` / `FULL_SYNC_RESPONSE` message types are defined in the protocol to support epidemic state dissemination (partially implemented) |
| **CAP theorem trade-off** | The system favours **Availability** and **Partition tolerance** (AP) over strong consistency; reads from any node may be temporarily stale during a network partition |
| **Decentralised replication** | `SensorUpdatePublisher` fans out local-origin updates to all known peers at a fixed interval, without a primary/replica distinction |

---

## Setup and Installation

### Prerequisites

- Python **3.11+** (developed on 3.14)
- Docker and Docker Compose (for containerised deployment)

### Local Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd distributed-sensor-hub

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy the example configuration
cp .env.example .env
# Edit .env to configure NODE_ID, PORT, BOOTSTRAP_PEERS, and sensors
```

### Configuration Reference

All configuration is provided through environment variables (or a `.env` file). The table below lists the key parameters.

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | — | Unique identifier for this node |
| `HOST` | `0.0.0.0` | TCP bind address |
| `PORT` | `9000` | TCP listen port for P2P communication |
| `BOOTSTRAP_PEERS` | — | Comma-separated list of `host:port` peers to contact at startup |
| `WEB_API_PORT` | `PORT + 1000` | HTTP API listen port |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FILE` | — | Optional path to a log file; logs to stderr if unset |
| `CLEAR_LOG` | `false` | If `true`, truncates the log file at startup |
| `SENSORS` | `0` | Number of sensors to load |
| `SENSOR_<N>_TYPE` | — | Sensor type: `numeric`, `boolean`, `wave`, `noise`, `spike`, `trend`, `categorical`, `incremental` |
| `SENSOR_<N>_NAME` | — | Human-readable sensor name |
| `SENSOR_<N>_PERIOD_MS` | — | Sampling interval in milliseconds |

Type-specific parameters (e.g., `SENSOR_<N>_MIN`, `SENSOR_<N>_MAX` for `numeric`) follow the same naming convention. See `.env.example` for a complete reference.

### Sensor Types

| Type | Description | Key Parameters |
|------|-------------|----------------|
| `numeric` | Uniform random value in \[min, max\] | `MIN`, `MAX`, `UNIT` |
| `boolean` | Bernoulli trial with probability `p_true` | `P_TRUE` |
| `wave` | Sinusoidal signal: `amplitude × sin(2π × frequency × t)` | `AMPLITUDE`, `FREQUENCY` |
| `noise` | Fixed baseline plus Gaussian noise | `BASE`, `NOISE` |
| `spike` | Baseline value with probabilistic spikes | `BASELINE`, `SPIKE_HEIGHT`, `P_SPIKE` |
| `trend` | Linear drift with additive noise: `start + slope × t + noise` | `START`, `SLOPE`, `NOISE` |
| `categorical` | Discrete value drawn uniformly from a set | `VALUES` |
| `incremental` | Monotonically increasing counter | `STEP` |

---

## Usage Instructions

### Running a Single Node (local)

```bash
# Start a standalone node (no bootstrap peers)
NODE_ID=node-1 HOST=0.0.0.0 PORT=9000 WEB_API_PORT=10000 \
  SENSORS=1 SENSOR_0_TYPE=numeric SENSOR_0_NAME=temperature \
  SENSOR_0_PERIOD_MS=1000 SENSOR_0_MIN=15 SENSOR_0_MAX=30 \
  python node.py
```

### Running a Two-Node Cluster (Docker Compose)

```bash
# Build and start a 2-node cluster
docker compose -f docker/docker-compose-base.yml up --build -d

# View logs
docker logs node-1 -f
docker logs node-2 -f
```

### Running a Six-Node Cluster (Docker Compose)

```bash
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
```

### Querying the REST API

Each node exposes two HTTP endpoints on `WEB_API_PORT` (default: `PORT + 1000`).

#### `GET /api/state`

Returns the full LWW state known to this node, grouped by originating node.

```bash
curl http://localhost:10000/api/state
```

**Example response:**

```json
{
  "node-1": {
    "temperature": {
      "value": 23.4,
      "ts_ms": 1714000000123,
      "origin": "node-1",
      "meta": { "unit": "°C", "period_ms": 2000 }
    }
  },
  "node-2": {
    "pressure": {
      "value": 1013.2,
      "ts_ms": 1714000000456,
      "origin": "node-2",
      "meta": { "unit": "hPa", "period_ms": 6000 }
    }
  }
}
```

#### `GET /api/updates`

Returns only the sensor readings that have changed since the last call to this endpoint (consumed read; the internal buffer is cleared after each response). Useful for incremental polling by monitoring dashboards.

```bash
curl http://localhost:10000/api/updates
```

The response schema is identical to `/api/state`.

---

## Testing

The test suite uses `pytest`. Test markers are defined in `pytest.ini` for each subsystem.

```bash
# Install test dependencies
pip install pytest

# Run the full test suite
pytest --maxfail=1

# Run with verbose output
pytest -v --maxfail=1

# Run tests for a specific module
pytest -m sensors
pytest -m protocol
pytest -m membership
pytest -m state
pytest -m networking
```

Available markers: `sensors`, `protocol`, `membership`, `state`, `networking`.

---

## Experimental Evaluation

The system was evaluated using multi-node Docker Compose deployments. Key observations:

- **State convergence:** In a 2-node cluster, after both nodes start and exchange `JOIN_REQUEST` / `PEER_LIST` messages, the LWW state on each node converges to include all sensors from both nodes within a few replication cycles (≤ 1 second under typical conditions given the 200 ms publish interval).
- **Concurrent updates:** Simultaneous updates to the same sensor key from different nodes are resolved deterministically by the LWW merge rule; no data corruption or divergence is observed in testing.
- **Fault tolerance:** If one node is stopped and restarted, it re-joins the cluster via `JOIN_REQUEST` and rapidly re-acquires the full state through incoming `SENSOR_UPDATE` broadcasts.

Quantitative benchmarking (latency, throughput, convergence time under varying cluster sizes) is outside the scope of this prototype.

---

## Limitations

- **Gossip protocol partially implemented.** The `GOSSIP_STATE`, `FULL_SYNC_REQUEST`, and `FULL_SYNC_RESPONSE` message types are defined in the protocol layer but their handlers are not fully wired. Replication currently relies on a direct broadcast (fan-out) from each publisher to all known peers, which does not scale to large cluster sizes.
- **No authentication or authorisation.** Any node that can reach the TCP port can send arbitrary messages. The system is intended for a controlled research environment and is not hardened for public deployment.
- **No persistent storage.** Node state is held entirely in memory. A node that restarts must re-learn the full state from peers via incoming broadcasts.
- **Static bootstrap configuration.** Bootstrap peers must be specified at startup. Dynamic peer discovery (e.g., via multicast or a rendezvous service) is not implemented.
- **Thread-per-connection concurrency.** The server spawns a new OS thread per inbound connection. This limits scalability to a moderate number of concurrent peers.
- **Phi-accrual failure detection not fully operational.** The `Peer` dataclass includes `phi` and `last_heartbeat` fields, but the accrual calculation and associated state transitions (`alive` → `suspected` → `dead`) are not driven by a background heartbeat monitor in the current implementation.

---

## Future Work

- **Complete gossip dissemination.** Implement the `GOSSIP_STATE` handler to enable epidemic propagation of state, reducing per-node bandwidth from O(N) to O(log N).
- **Phi-accrual failure detector.** Implement a background heartbeat thread that sends `PING` messages and updates `Peer.phi` scores to drive automatic failure detection and peer eviction.
- **Persistent state.** Add a write-ahead log or snapshot mechanism so that a restarting node can restore its last known state without relying entirely on peer replication.
- **Dynamic membership.** Support peer discovery without static bootstrap configuration, for example via mDNS, DNS-SD, or a lightweight rendezvous service.
- **Asynchronous I/O.** Replace the thread-per-connection model with `asyncio` to improve connection scalability.
- **Security layer.** Add mutual TLS authentication between nodes and optionally expose the HTTP API through an authenticated reverse proxy.
- **Quantitative evaluation.** Measure convergence latency, message overhead, and throughput under controlled network conditions (varying latency, partition scenarios) using a reproducible benchmarking harness.

---

## References

1. Brewer, E. A. (2000). *Towards robust distributed systems*. PODC Keynote.
2. Gilbert, S., & Lynch, N. (2002). *Brewer's conjecture and the feasibility of consistent, available, partition-tolerant web services*. ACM SIGACT News, 33(2), 51–59.
3. Shapiro, M., Preguiça, N., Baquero, C., & Zawirski, M. (2011). *Conflict-free replicated data types*. In Proc. SSS 2011, LNCS 6976, pp. 386–400. Springer.
4. Vogels, W. (2009). *Eventually consistent*. Communications of the ACM, 52(1), 40–44.
5. Hayashibara, N., Défago, X., Yared, R., & Katayama, T. (2004). *The Φ accrual failure detector*. In Proc. SRDS 2004, pp. 66–78. IEEE.
6. Demers, A., et al. (1987). *Epidemic algorithms for replicated database maintenance*. In Proc. PODC 1987, pp. 1–12. ACM.