"""Deterministic state-convergence test against a real Docker cluster."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import time

import pytest

from tests.integration.docker_cluster_harness import DockerClusterHarness
from tests.integration.docker_requirements import skip_unless_docker_accessible
from utils.typing import JsonObject


DETERMINISTIC_COMPOSE = Path("docker/docker-compose-integration-deterministic.yml")
LOGS_ON_FAILURE = Path("logs/docker-deterministic-convergence-failure.log")


@dataclass(frozen=True)
class _SensorPlan:
    sensor_name: str
    index: int
    period_ms: int
    seed: int
    max_updates: int
    start_ts_ms: int
    unit: str

    @property
    def logical_sensor_id(self) -> str:
        return f"{self.sensor_name}@{self.index}"


@dataclass(frozen=True)
class _NodePlan:
    node_id: str
    sensors: tuple[_SensorPlan, ...]


NODE_PLANS: tuple[_NodePlan, ...] = (
    _NodePlan(
        node_id="node1",
        sensors=(
            _SensorPlan(
                sensor_name="unique_node1",
                index=0,
                period_ms=20,
                seed=11,
                max_updates=4,
                start_ts_ms=1700000000000,
                unit="itest",
            ),
            _SensorPlan(
                sensor_name="unique_aux_node1",
                index=1,
                period_ms=30,
                seed=101,
                max_updates=3,
                start_ts_ms=1700000001000,
                unit="itest",
            ),
        ),
    ),
    _NodePlan(
        node_id="node2",
        sensors=(
            _SensorPlan(
                sensor_name="unique_node2",
                index=0,
                period_ms=20,
                seed=12,
                max_updates=4,
                start_ts_ms=1700000000000,
                unit="itest",
            ),
            _SensorPlan(
                sensor_name="unique_aux_node2",
                index=1,
                period_ms=30,
                seed=102,
                max_updates=3,
                start_ts_ms=1700000001000,
                unit="itest",
            ),
        ),
    ),
    _NodePlan(
        node_id="node3",
        sensors=(
            _SensorPlan(
                sensor_name="unique_node3",
                index=0,
                period_ms=20,
                seed=13,
                max_updates=4,
                start_ts_ms=1700000000000,
                unit="itest",
            ),
            _SensorPlan(
                sensor_name="unique_aux_node3",
                index=1,
                period_ms=30,
                seed=103,
                max_updates=3,
                start_ts_ms=1700000001000,
                unit="itest",
            ),
        ),
    ),
    _NodePlan(
        node_id="node4",
        sensors=(
            _SensorPlan(
                sensor_name="unique_node4",
                index=0,
                period_ms=20,
                seed=14,
                max_updates=4,
                start_ts_ms=1700000000000,
                unit="itest",
            ),
            _SensorPlan(
                sensor_name="unique_aux_node4",
                index=1,
                period_ms=30,
                seed=104,
                max_updates=3,
                start_ts_ms=1700000001000,
                unit="itest",
            ),
        ),
    ),
)


def _wait_until(
    condition,
    *,
    timeout_s: float,
    interval_s: float,
    description: str,
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except Exception as exc:  # pragma: no cover - diagnostics path
            last_error = exc
        time.sleep(interval_s)

    if last_error is None:
        raise TimeoutError(f"Timed out waiting for {description}")
    raise TimeoutError(
        f"Timed out waiting for {description}: {type(last_error).__name__}: {last_error}"
    )


def _extract_node_state(snapshot: JsonObject, *, node_id: str) -> JsonObject:
    per_node = snapshot.get(node_id)
    if not isinstance(per_node, dict):
        raise AssertionError(f"Snapshot for {node_id} missing dict payload: {snapshot}")
    return per_node


def _build_expected_winning_state() -> JsonObject:
    winners: dict[str, tuple[str, float, int, JsonObject]] = {}

    for node_plan in NODE_PLANS:
        origin = node_plan.node_id
        for sensor in node_plan.sensors:
            rng = random.Random(sensor.seed)
            for index in range(sensor.max_updates):
                value = round(rng.uniform(0.0, 100.0), 6)
                ts_ms = sensor.start_ts_ms + (index * sensor.period_ms)
                logical_sensor_id = sensor.logical_sensor_id
                meta: JsonObject = {"unit": sensor.unit, "period_ms": sensor.period_ms}

                current = winners.get(logical_sensor_id)
                if current is None:
                    winners[logical_sensor_id] = (origin, value, ts_ms, meta)
                    continue
                current_origin, _, current_ts_ms, _ = current
                if ts_ms > current_ts_ms:
                    winners[logical_sensor_id] = (origin, value, ts_ms, meta)
                    continue
                if ts_ms == current_ts_ms and origin > current_origin:
                    winners[logical_sensor_id] = (origin, value, ts_ms, meta)

    expected: JsonObject = {}
    for logical_sensor_id, (origin, value, ts_ms, meta) in winners.items():
        global_sensor_id = f"{origin}:{logical_sensor_id}"
        row: JsonObject = {
            "value": value,
            "ts_ms": ts_ms,
            "origin": origin,
            "meta": meta,
        }
        expected[global_sensor_id] = row

    return dict(sorted(expected.items(), key=lambda kv: kv[0]))


@pytest.mark.integration
def test_docker_deterministic_state_convergence() -> None:
    """Assert deterministic LWW convergence over real Dockerized nodes."""
    skip_unless_docker_accessible()
    harness = DockerClusterHarness(compose_file=DETERMINISTIC_COMPOSE)
    expected = _build_expected_winning_state()

    with harness.running_cluster(
        build=True,
        readiness_timeout_s=60.0,
        dump_logs_on_failure=True,
        failure_logs_file=LOGS_ON_FAILURE,
    ):
        # Wait until finite sensors have completed local emissions on each node.
        # We detect completion by checking each node's unique sensor winner ts.
        def sensors_finished() -> bool:
            for node_plan in NODE_PLANS:
                state = harness.fetch_state(node_plan.node_id, timeout_s=0.8)
                per_node = _extract_node_state(state, node_id=node_plan.node_id)
                unique_plan = node_plan.sensors[0]
                expected_final_ts = unique_plan.start_ts_ms + (
                    (unique_plan.max_updates - 1) * unique_plan.period_ms
                )
                key = f"{node_plan.node_id}:{unique_plan.logical_sensor_id}"
                row = per_node.get(key)
                if not isinstance(row, dict):
                    return False
                if row.get("ts_ms") != expected_final_ts:
                    return False
            return True

        _wait_until(
            sensors_finished,
            timeout_s=25.0,
            interval_s=0.2,
            description="finite deterministic sensors to complete",
        )

        latest_actual_by_node: dict[str, JsonObject] = {}

        def converged_to_expected() -> bool:
            nonlocal latest_actual_by_node
            current: dict[str, JsonObject] = {}
            for node_id in harness.node_ids:
                snapshot = harness.fetch_state(node_id, timeout_s=0.8)
                current[node_id] = _extract_node_state(snapshot, node_id=node_id)
            latest_actual_by_node = current

            states = list(current.values())
            if not states:
                return False
            first = states[0]
            if any(state != first for state in states[1:]):
                return False
            return first == expected

        _wait_until(
            converged_to_expected,
            timeout_s=25.0,
            interval_s=0.25,
            description="docker state convergence to expected LWW winners",
        )

        assert latest_actual_by_node, "No state snapshots collected"
        final_state = next(iter(latest_actual_by_node.values()))
        assert final_state == expected
        assert set(expected.keys()).issubset(set(final_state.keys()))
