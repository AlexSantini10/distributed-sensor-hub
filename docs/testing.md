# Testing

Technical test guide for local development and Docker validation.

## Local test commands

```bash
pytest --maxfail=1
pytest -v --maxfail=1
pytest -m protocol
python -m pytest tests/state/test_lww.py -q
```

Pytest markers are defined in [pytest.ini](../pytest.ini).

## Deterministic convergence (integration)

This test runs a real 6-node in-process cluster and verifies replicated **state convergence** (`/api/state`), including expected LWW winners.

```bash
python -m pytest tests/integration/test_deterministic_state_convergence.py -q -s
```

Expected runtime:

- local machine: ~10-25 s
- CI runner: ~15-40 s

Scope limits:

- validates state convergence, not full membership stability semantics
- timing is deadline/polling-based, so duration depends on host load

## Docker-backed integration checks

The Docker-backed suite builds real node containers and verifies deterministic convergence, crash/restart recovery, and temporary partition reconciliation.

```bash
python -m pytest \
  tests/integration/test_docker_crash_restart_recovery.py \
  tests/integration/test_docker_deterministic_state_convergence.py \
  tests/integration/test_docker_partition_reconciliation.py \
  -vv
```

The integration workflow also builds the release image and runs `docker/smoke-test.sh` against its state API and dashboard.

## Chaos/recovery scenario

Use `scripts/compose_chaos.py` to stop/restart one service in a running topology.

Example (`node3`, 6-node topology):

```bash
docker compose -f docker/docker-compose-6-nodes.yml up --build -d
python scripts/compose_chaos.py \
  --compose-file docker/docker-compose-6-nodes.yml \
  --service node3 \
  --down-seconds 20 \
  --up-seconds 40 \
  --cycles 5
docker compose -f docker/docker-compose-6-nodes.yml down
```

## Fault-injection knobs

- sensor latency: `SENSOR_<i>_LATENCY_MS`, `SENSOR_<i>_LATENCY_JITTER_MS`
- network delay/loss: `NETWORK_DELAY_MS`, `NETWORK_DELAY_JITTER_MS`, `NETWORK_DELAY_SPIKE_PROB`, `NETWORK_DELAY_SPIKE_MS`, `NETWORK_PACKET_LOSS_PROB`
- replication cadence/fanout: `GOSSIP_SYNC_INTERVAL_MS`, `GOSSIP_PUSH_*`, `GOSSIP_PULL_*`

## CI references

- [unit test and Pyright workflow](../.github/workflows/unit-tests.yml)
- [integration workflow](../.github/workflows/integration-tests.yml)
- [documentation workflow](../.github/workflows/docs.yml)
- [Docker CD workflow](../.github/workflows/docker-cd.yml)
