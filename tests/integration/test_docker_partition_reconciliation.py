"""Temporary Docker partition test with deterministic protocol injection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import pytest

from tests.integration.docker_cluster_harness import DockerClusterHarness
from utils.typing import JsonObject


PARTITION_COMPOSE = Path("docker/docker-compose-integration-tests.yml")
LOGS_ON_FAILURE = Path("logs/docker-partition-reconciliation-failure.log")


@dataclass(frozen=True)
class _InjectedUpdate:
    target_node_id: str
    sensor_id: str
    value: object
    ts_ms: int
    origin: str
    meta: JsonObject


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


def _build_expected_winners(updates: tuple[_InjectedUpdate, ...]) -> JsonObject:
    winners: dict[str, _InjectedUpdate] = {}
    for update in updates:
        current = winners.get(update.sensor_id)
        if current is None:
            winners[update.sensor_id] = update
            continue
        if update.ts_ms > current.ts_ms:
            winners[update.sensor_id] = update
            continue
        if update.ts_ms == current.ts_ms and update.origin > current.origin:
            winners[update.sensor_id] = update

    expected: dict[str, JsonObject] = {}
    for sensor_id, winner in winners.items():
        key = f"{winner.origin}:{sensor_id}"
        expected[key] = {
            "value": winner.value,
            "ts_ms": winner.ts_ms,
            "origin": winner.origin,
            "meta": winner.meta,
        }
    return dict(sorted(expected.items(), key=lambda kv: kv[0]))


@pytest.mark.integration
def test_docker_temporary_partition_reconciliation() -> None:
    """Assert cluster reconciliation after real Docker network partition and heal."""
    harness = DockerClusterHarness(compose_file=PARTITION_COMPOSE)

    updates: tuple[_InjectedUpdate, ...] = (
        # Conflict intentionally injected on both sides while partitioned.
        _InjectedUpdate(
            target_node_id="node1",
            sensor_id="partition_conflict@0",
            value="a-side",
            ts_ms=1700000100000,
            origin="node1",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node4",
            sensor_id="partition_conflict@0",
            value="b-side",
            ts_ms=1700000100000,
            origin="node4",
            meta={"unit": "itest", "period_ms": 25},
        ),
        # Additional deterministic winners from both partitions.
        _InjectedUpdate(
            target_node_id="node2",
            sensor_id="partition_left_only@0",
            value=111,
            ts_ms=1700000100100,
            origin="node2",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node3",
            sensor_id="partition_right_only@0",
            value=222,
            ts_ms=1700000100200,
            origin="node3",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node1",
            sensor_id="stable_left@0",
            value=1.5,
            ts_ms=1700000100300,
            origin="node1",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node4",
            sensor_id="stable_right@0",
            value=2.5,
            ts_ms=1700000100400,
            origin="node4",
            meta={"unit": "itest", "period_ms": 25},
        ),
    )
    expected = _build_expected_winners(updates)

    with harness.running_cluster(
        build=True,
        readiness_timeout_s=60.0,
        dump_logs_on_failure=True,
        failure_logs_file=LOGS_ON_FAILURE,
    ):
        harness.partition_subgroups()

        harness.inject_sensor_updates(
            [
                {
                    "target_node_id": update.target_node_id,
                    "sensor_id": update.sensor_id,
                    "value": update.value,
                    "ts_ms": update.ts_ms,
                    "origin": update.origin,
                    "meta": update.meta,
                }
                for update in updates
            ]
        )

        # During partition, subgroup states should temporarily diverge.
        def divergence_observable() -> bool:
            current = {
                node_id: _extract_node_state(harness.fetch_state(node_id, timeout_s=0.8), node_id=node_id)
                for node_id in harness.node_ids
            }
            states = list(current.values())
            if not states:
                return False
            first = states[0]
            return any(state != first for state in states[1:])

        _wait_until(
            divergence_observable,
            timeout_s=8.0,
            interval_s=0.25,
            description="temporary divergence during partition",
        )

        harness.heal_subgroups()

        latest_actual_by_node: dict[str, JsonObject] = {}

        def converged_to_expected() -> bool:
            nonlocal latest_actual_by_node
            current = {
                node_id: _extract_node_state(harness.fetch_state(node_id, timeout_s=0.8), node_id=node_id)
                for node_id in harness.node_ids
            }
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
            timeout_s=30.0,
            interval_s=0.25,
            description="post-heal reconciliation to expected LWW winners",
        )

        assert latest_actual_by_node, "No post-heal snapshots collected"
        final_state = next(iter(latest_actual_by_node.values()))
        assert final_state == expected
        assert set(final_state.keys()) == set(expected.keys())
