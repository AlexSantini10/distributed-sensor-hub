# Architecture and Design

## System overview

The system consists of independent nodes running the same software stack. Nodes discover peers through bootstrap addresses and gossip-style membership exchange, then replicate sensor updates across the cluster.

## Main subsystems

### Sensors (`sensors/`)

Sensors are periodic daemon threads that emit readings into a shared event queue. The project currently includes numeric, boolean, noise, wave, trend, spike, categorical, and incremental sensors.

### State replication (`state/`)

`NodeStateWorker` maintains the merged in-memory state using Last-Write-Wins semantics. It also exposes separate update streams for the HTTP API and for outbound replication.

`SensorUpdatePublisher` polls replication updates and broadcasts `SENSOR_UPDATE` messages to known peers.

### Membership (`membership/`)

`PeerTable` is the in-memory registry of known peers. `JOIN_REQUEST` and `PEER_LIST` handlers support peer discovery and transitive cluster expansion.

### Protocol (`protocol/`)

All node-to-node traffic is wrapped in a common `Message` envelope:

```text
Message {
    msg_type  : MessageType
    sender_id : str
    payload   : dict
    timestamp : int
}
```

The dispatcher maps each `MessageType` to a dedicated handler.

### Networking (`networking/`)

`TcpServer` handles inbound framed messages, while `TcpClient` maintains per-peer outbound connections with reconnection support.

### Web API (`webapi/`)

The HTTP API exposes:

- `GET /api/state`
- `GET /api/updates`

## Technologies used

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.14 | Main implementation language |
| `python-dotenv` | >= 1.0 | Environment-driven configuration |
| `pytest` | >= 9.0 | Unit and integration testing |
| Docker / Docker Compose | n/a | Containerized deployment |
| `socket` | stdlib | TCP transport |
| `threading` / `queue` | stdlib | Concurrency primitives |
| `http.server` | stdlib | REST API server |

## Design choices

### No centralized coordinator

Every node is autonomous. There is no leader or broker, which removes a central dependency from the data path.

### LWW CRDT for state replication

The system uses Last-Write-Wins conflict resolution to keep sensor state convergent without consensus.

### Environment-variable configuration

Node identity, network endpoints, bootstrap peers, and sensors are configured through environment variables so the same image can serve different node roles.

### Two independent update streams

The state worker separates updates intended for the Web API from updates intended for replication, preventing one consumer from starving the other.

### TCP with length-prefix framing

Messages are framed with a 4-byte big-endian length header, which provides reliable boundaries over a stream-oriented transport.

## Distributed systems concepts applied

| Concept | Current usage |
|---------|---------------|
| Gossip / Epidemic dissemination | Membership propagation through `JOIN_REQUEST` and `PEER_LIST` |
| CRDT (LWW register) | Conflict-free state merge in the state worker |
| Eventual consistency | Sensor state converges asynchronously across nodes |
| Peer-to-peer communication | Symmetric TCP communication without hierarchy |
| Decentralized membership | Peer discovery without a directory server |
| Fault-tolerant networking | Reconnection and keepalive support in the TCP client |
| State partitioning | Sensor updates carry origin information to avoid ambiguity |
| Multi-threaded concurrency | Explicit locking and queue-based worker coordination |
