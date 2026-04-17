# Testing Guide

This guide collects the local test workflow, Docker smoke checks, and manual resilience scenarios for the project.

## Local test suite

```bash
pytest --maxfail=1
pytest -v --maxfail=1
pytest -m protocol
python -m pytest tests/state/test_lww.py -q
```

Available pytest markers are defined in [pytest.ini](../pytest.ini):

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

## Docker topologies covered by this guide

- `docker/docker-compose-base.yml`: minimal smoke topology
- `docker/docker-compose-6-nodes.yml`: medium-size cluster for resilience and convergence checks
- `docker/docker-compose-12-nodes.yml`: larger cluster for scale-oriented manual validation

## Integration and Docker smoke checks

### Base topology

```bash
docker compose -f docker/docker-compose-base.yml up --build -d
python tests/integration/verify_cluster.py --timeout 60 --interval 2
docker compose -f docker/docker-compose-base.yml down
```

### 6-node topology

```bash
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
python tests/integration/verify_cluster.py --timeout 120 --interval 2
docker compose -f docker/docker-compose-6-nodes.yml down
```

### 12-node topology

The current `verify_cluster.py` smoke test polls the default HTTP endpoints only, so for the 12-node topology use it as a basic sanity check together with the monitoring UI in [web/index.html](../web/index.html).

```bash
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
python tests/integration/verify_cluster.py --timeout 120 --interval 2
docker compose -f docker/docker-compose-12-nodes.yml down
```

## Timed crash and recovery with Docker Compose

`manual_tests/compose_chaos.py` periodically stops and restarts one Docker Compose service that is already running.

Notes:

- `--service` uses the Compose service name (`node1`, `node2`, ...), not `container_name`
- `--cycles 0` means infinite loop
- `--initial-delay-seconds N` adds a wait before the first stop

### Example: 6 nodes, flap one node

PowerShell:

```powershell
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-6-nodes.yml `
  --service node3 `
  --down-seconds 20 `
  --up-seconds 40 `
  --cycles 5
docker compose -f docker/docker-compose-6-nodes.yml down
```

Linux/macOS:

```bash
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node3 \
  --down-seconds 20 \
  --up-seconds 40 \
  --cycles 5
docker compose -f docker/docker-compose-6-nodes.yml down
```

### Example: 12 nodes, flap one node

PowerShell:

```powershell
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-12-nodes.yml `
  --service node10 `
  --down-seconds 30 `
  --up-seconds 45 `
  --cycles 4
docker compose -f docker/docker-compose-12-nodes.yml down
```

Linux/macOS:

```bash
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-12-nodes.yml \
  --service node10 \
  --down-seconds 30 \
  --up-seconds 45 \
  --cycles 4
docker compose -f docker/docker-compose-12-nodes.yml down
```

## Simulating unstable connectivity

For phi-accrual and resilience tests, combine:

- sensor latency: `SENSOR_<i>_LATENCY_MS`, `SENSOR_<i>_LATENCY_JITTER_MS`
- network delay/loss: `NETWORK_DELAY_MS`, `NETWORK_DELAY_JITTER_MS`, `NETWORK_DELAY_SPIKE_PROB`, `NETWORK_DELAY_SPIKE_MS`, `NETWORK_PACKET_LOSS_PROB`
- push-pull fanout/cadence: `GOSSIP_SYNC_INTERVAL_MS`, `GOSSIP_PUSH_RATIO`, `GOSSIP_PUSH_MIN_PEERS`, `GOSSIP_PULL_RATIO`, `GOSSIP_PULL_MIN_PEERS`, `GOSSIP_PULL_EVERY_ROUNDS`

Example environment values:

PowerShell:

```powershell
$env:NETWORK_DELAY_MS=40
$env:NETWORK_DELAY_JITTER_MS=30
$env:NETWORK_DELAY_SPIKE_PROB=0.1
$env:NETWORK_DELAY_SPIKE_MS=250
$env:NETWORK_PACKET_LOSS_PROB=0.02
$env:SENSOR_0_LATENCY_MS=60
$env:SENSOR_0_LATENCY_JITTER_MS=40
```

Linux/macOS:

```bash
export NETWORK_DELAY_MS=40 NETWORK_DELAY_JITTER_MS=30
export NETWORK_DELAY_SPIKE_PROB=0.1 NETWORK_DELAY_SPIKE_MS=250
export NETWORK_PACKET_LOSS_PROB=0.02
export SENSOR_0_LATENCY_MS=60 SENSOR_0_LATENCY_JITTER_MS=40
export GOSSIP_SYNC_INTERVAL_MS=1000
export GOSSIP_PUSH_RATIO=0.3 GOSSIP_PUSH_MIN_PEERS=2
export GOSSIP_PULL_RATIO=0.15 GOSSIP_PULL_MIN_PEERS=1
export GOSSIP_PULL_EVERY_ROUNDS=3
```

## Suggested manual scenarios

### Scenario: start the 6-node Docker topology and simulate connectivity jumps on a couple of nodes

Use two terminals.

Terminal 1:

```powershell
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
```

Terminal 2, PowerShell:

```powershell
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-6-nodes.yml `
  --service node3 `
  --down-seconds 15 `
  --up-seconds 30 `
  --cycles 4
```

Terminal 2, Linux/macOS:

```bash
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node3 \
  --down-seconds 15 \
  --up-seconds 30 \
  --cycles 4
```

After the first loop starts, trigger a second unstable node:

PowerShell:

```powershell
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-6-nodes.yml `
  --service node5 `
  --down-seconds 10 `
  --up-seconds 35 `
  --cycles 4 `
  --initial-delay-seconds 8
```

Linux/macOS:

```bash
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node5 \
  --down-seconds 10 \
  --up-seconds 35 \
  --cycles 4 \
  --initial-delay-seconds 8
```

Suggested observations:

- monitor the cluster through [web/index.html](../web/index.html)
- check whether peers move through `alive`, `suspected`, and recovery states
- run `python tests/integration/verify_cluster.py --timeout 120 --interval 2` after the chaos window

Cleanup:

```bash
docker compose -f docker/docker-compose-6-nodes.yml down
```

### Scenario: start the 12-node Docker topology and simulate connectivity jumps on two nodes

```powershell
docker compose -f docker/docker-compose-12-nodes.yml up --build -d
```

Then, in separate terminals.

PowerShell, terminal A:

```powershell
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-12-nodes.yml `
  --service node8 `
  --down-seconds 20 `
  --up-seconds 35 `
  --cycles 5
```

PowerShell, terminal B:

```powershell
python manual_tests/compose_chaos.py `
  --compose-file docker/docker-compose-12-nodes.yml `
  --service node11 `
  --down-seconds 25 `
  --up-seconds 50 `
  --cycles 4 `
  --initial-delay-seconds 12
```

Linux/macOS, terminal A:

```bash
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-12-nodes.yml \
  --service node8 \
  --down-seconds 20 \
  --up-seconds 35 \
  --cycles 5
```

Linux/macOS, terminal B:

```bash
python manual_tests/compose_chaos.py \
  --compose-file docker/docker-compose-12-nodes.yml \
  --service node11 \
  --down-seconds 25 \
  --up-seconds 50 \
  --cycles 4 \
  --initial-delay-seconds 12
```

Suggested observations:

- monitor the larger topology through [web/index.html](../web/index.html)
- verify that the remaining nodes keep serving merged state while the unstable nodes recover
- review the generated logs under `logs/`

Cleanup:

```bash
docker compose -f docker/docker-compose-12-nodes.yml down
```

## CI references

- [.github/workflows/pytest.yml](../.github/workflows/pytest.yml)
- [.github/workflows/integration-tests.yml](../.github/workflows/integration-tests.yml)
