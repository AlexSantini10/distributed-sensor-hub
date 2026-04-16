# Runtime Module

`runtime` is the node orchestration layer. It wires process bootstrap, local state, TCP networking, protocol handlers, membership, heartbeat, sensors, replication, and the monitoring API into one runnable node.

The module should contain coordination code only. Domain logic belongs in the dedicated packages: `state/`, `protocol/`, `membership/`, `networking/`, `sensors/`, `gossip/`, and `webapi/`.

## Table of Contents

- [Responsibilities](#responsibilities)
- [Files](#files)
- [Startup Order](#startup-order)
- [Shutdown Order](#shutdown-order)
- [Main Components](#main-components)
  - [`NodeApplication`](#nodeapplication)
  - [`setup_node_networking(...)`](#setup_node_networking)
  - [Bootstrap Membership](#bootstrap-membership)
  - [`HeartbeatSender`](#heartbeatsender)
  - [Process Bootstrap](#process-bootstrap)
- [Runtime Flows](#runtime-flows)
- [Runtime Configuration](#runtime-configuration)
- [Programmatic Use](#programmatic-use)
- [Tests](#tests)
- [Maintenance Notes](#maintenance-notes)

## Responsibilities

- Configure early process behavior before the node is built.
- Assemble the runtime TCP/protocol stack.
- Register configured bootstrap peers.
- Start membership bootstrap through `JOIN_REQUEST`.
- Request initial full synchronization from bootstrap peers.
- Run periodic heartbeat, membership gossip, and phi-accrual evaluation.
- Start local sensors and outbound state replication.
- Start the Web API after the main runtime state is ready.
- Stop all subsystems in dependency-aware order.

## Files

| File | Purpose |
|------|---------|
| `application.py` | Defines `NodeApplication`, the lifecycle container for startup, steady state, and shutdown. |
| `networking.py` | Builds `TcpClient`, `TcpServer`, protocol dispatcher, `PeerTable`, bootstrap peers, and dynamic peer registration. |
| `heartbeat.py` | Defines `HeartbeatSender`, the background loop for phi evaluation, gossip, and `PING` emission. |
| `bootstrap.py` | Configures early logging, global exception hooks, and optional log-file truncation. |
| `__init__.py` | Package marker and module-level documentation. |

## Startup Order

`node.py` loads configuration, initializes logging, constructs `NodeApplication`, and calls `start()`.

Startup sequence:

1. Start `NodeStateWorker`.
2. Build networking with `setup_node_networking(...)`.
3. Start `TcpServer`.
4. Seed membership and send `JOIN_REQUEST` to bootstrap peers.
5. Send `FULL_SYNC_REQUEST` to bootstrap peers.
6. Start `HeartbeatSender`.
7. Load and start configured sensors.
8. Start `SensorUpdatePublisher`.
9. Start `WebAPIServer`.

This order ensures state processing is available before network or sensor input can arrive. If startup fails, `start()` calls `stop()` and re-raises the original exception.

## Shutdown Order

`NodeApplication.stop()` is idempotent and best-effort. Each subsystem is stopped even if an earlier stop step fails.

Shutdown sequence:

1. `HeartbeatSender`
2. `SensorUpdatePublisher`
3. `SensorManager`
4. `WebAPIServer`
5. `NodeStateWorker`
6. `TcpServer` and `TcpClient`

Traffic-producing components are stopped before state and transport components.

## Main Components

### `NodeApplication`

Owns the runtime instances for one node:

- `SensorEventQueue`
- `NodeStateWorker`
- `TcpClient`
- `TcpServer`
- `PeerTable`
- `SensorManager`
- `SensorUpdatePublisher`
- `HeartbeatSender`
- `WebAPIServer`
- bootstrap peer list

Main methods:

| Method | Purpose |
|--------|---------|
| `start()` | Starts all subsystems in dependency order. |
| `run_forever()` | Keeps the process alive until interruption or fatal error. |
| `stop()` | Stops all started subsystems. |

### `setup_node_networking(...)`

Creates the node communication stack:

- outbound `TcpClient`;
- `ClientPeerRegistry` for duplicate-safe peer registration;
- configured bootstrap peers;
- protocol dispatcher and handlers through `protocol.setup.setup_protocol(...)`;
- shared `PeerTable`;
- inbound `TcpServer`.

The `on_peer_discovered(...)` callback registers newly discovered peers in the TCP client and sends a reciprocal `JOIN_REQUEST`.

### Bootstrap Membership

Bootstrap has two separate concerns:

1. `build_bootstrap_peers(...)` registers configured `host:port` endpoints in `TcpClient`.
2. `bootstrap_membership(...)` sends `JOIN_REQUEST` messages to those endpoints.

Endpoint-only bootstrap peers use placeholder IDs:

```text
bootstrap@host:port
```

`seed_peer_table(...)` skips those placeholders so temporary bootstrap identities do not enter membership state.

### `HeartbeatSender`

Runs in a daemon thread named `heartbeat-sender`.

Each round:

1. evaluates phi-accrual status through `PeerTable.evaluate_failure_detector(...)`;
2. logs membership transitions;
3. builds one `PING`;
4. reads the current peer snapshot;
5. publishes membership gossip through `publish_membership_gossip(...)`;
6. sends `PING` to each known peer.

`interval_ms` is converted to seconds and clamped to a minimum of `0.001`.

### Process Bootstrap

`bootstrap.py` must run before `NodeApplication` construction:

| Function | Purpose |
|----------|---------|
| `setup_bootstrap_logging()` | Installs minimal stderr logging for early failures. |
| `install_global_exception_hooks()` | Logs unhandled main-thread and worker-thread exceptions. |
| `clear_log_file_if_requested(...)` | Truncates the configured log file when enabled. |

## Runtime Flows

Node startup:

```text
node.py
  -> load_config()
  -> setup_logging(...)
  -> NodeApplication.start()
      -> NodeStateWorker.start()
      -> setup_node_networking(...)
      -> TcpServer.start()
      -> JOIN_REQUEST to bootstrap peers
      -> FULL_SYNC_REQUEST to bootstrap peers
      -> HeartbeatSender.start()
      -> SensorManager.start_all()
      -> SensorUpdatePublisher.start()
      -> WebAPIServer.start()
  -> NodeApplication.run_forever()
```

Peer discovery:

```text
discovered peer
  -> on_peer_discovered(peer)
  -> ClientPeerRegistry.ensure_peer(...)
  -> TcpClient.add_peer(...)
  -> reciprocal JOIN_REQUEST
```

Heartbeat:

```text
heartbeat round
  -> evaluate phi
  -> update alive/suspected/dead status
  -> publish GOSSIP_STATE
  -> send PING
```

If a peer advertises `0.0.0.0`, `resolve_peer_host(...)` uses `node_id` as the connectable host. This supports Docker topologies where service names are routable.

## Runtime Configuration

`runtime` consumes a validated `utils.config.Config`.

| Field | Runtime use |
|-------|-------------|
| `node_id` | Local identity for messages, membership, and state origin. |
| `host` | Bind address for TCP and HTTP servers. |
| `port` | Peer-to-peer TCP port. |
| `bootstrap_peers` | Initial peer endpoints for join and full sync. |
| `web_api_port` | HTTP monitoring port. |
| `heartbeat_interval_ms` | Heartbeat loop interval. |
| `phi_threshold_suspect` | Phi threshold for `suspected`. |
| `phi_threshold_dead` | Phi threshold for `dead`. |
| `phi_initial_interval_s` | Initial expected heartbeat interval. |
| `replication_delta_maxlen` | Replication delta buffer size. |
| `network_delay_ms` | Base artificial outbound delay. |
| `network_delay_jitter_ms` | Artificial delay jitter. |
| `network_delay_spike_prob` | Delay spike probability. |
| `network_delay_spike_ms` | Extra delay during a spike. |
| `network_packet_loss_prob` | Outbound packet drop probability. |
| `sensors` | Local sensor definitions. |

## Programmatic Use

Normal execution should use:

```bash
python node.py
```

Controlled tests can instantiate the application directly:

```python
from runtime.application import NodeApplication
from utils.config import load_config
from utils.logging import get_logger, setup_logging

config = load_config()
setup_logging(config.node_id, config.log_level, config.log_file)

log = get_logger(__name__, config.node_id)
app = NodeApplication(config=config, log=log)

try:
    app.start()
    app.run_forever()
finally:
    app.stop()
```

## Tests

Runtime-specific tests live in `tests/runtime/`.

```bash
pytest tests/runtime -q
pytest -m runtime
```

Current coverage:

- bootstrap placeholder filtering in `seed_peer_table(...)`;
- non-blocking heartbeat startup;
- `PING` and `GOSSIP_STATE` emission;
- phi transition logging.

## Maintenance Notes

- Keep runtime code focused on wiring and lifecycle.
- Add a matching shutdown step for every subsystem started by `NodeApplication`.
- Stop traffic producers before stopping transport.
- Start state consumers before accepting network or sensor input.
- Let startup failures propagate after cleanup.
