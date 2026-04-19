"""Deterministic real-cluster check for replicated state convergence."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import pytest

from tests.integration.cluster_harness import (
    NodeHandle,
    attach_finite_sensor,
    fetch_state,
    start_cluster,
    stop_cluster,
    wait_for_readiness,
    wait_until,
)
from tests.integration.finite_test_sensor import FiniteTestSensor


@dataclass(frozen=True)
class _EmittedUpdate:
    """Represent one emitted update enriched with node origin."""

    sensor_id: str
    value: object
    ts_ms: int
    origin: str
    meta: dict[str, object]


def _extract_node_state(snapshot: dict, node_id: str) -> dict[str, dict]:
    """Return one node's state payload from ``/api/state``."""
    per_node = snapshot.get(node_id)
    if not isinstance(per_node, dict):
        raise AssertionError(f"Snapshot for {node_id} missing dict payload: {snapshot}")
    return per_node


def _build_expected_winning_state(updates: list[_EmittedUpdate]) -> dict[str, dict]:
    """Compute expected winners with the runtime LWW rule on ``(ts_ms, origin)``."""
    winners: dict[str, _EmittedUpdate] = {}
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

    expected: dict[str, dict] = {}
    for sensor_id, winner in winners.items():
        global_sensor_id = f"{winner.origin}:{sensor_id}"
        expected[global_sensor_id] = {
            "value": winner.value,
            "ts_ms": winner.ts_ms,
            "origin": winner.origin,
            "meta": winner.meta,
        }
    return dict(sorted(expected.items(), key=lambda kv: kv[0]))


def _collect_emitted_updates(
    sensors: list[tuple[NodeHandle, FiniteTestSensor]],
) -> list[_EmittedUpdate]:
    """Collect all emitted readings from finite sensors."""
    collected: list[_EmittedUpdate] = []
    for node, sensor in sensors:
        for reading in sensor.emitted_readings:
            collected.append(
                _EmittedUpdate(
                    sensor_id=reading.sensor_id,
                    value=reading.value,
                    ts_ms=reading.observed_at_ms,
                    origin=node.node_id,
                    meta={
                        "unit": reading.meta.get("unit"),
                        "period_ms": reading.meta.get("period_ms"),
                    },
                )
            )
    return collected


def _diagnose_state_mismatch(
    *,
    expected: dict[str, dict],
    actual_by_node: dict[str, dict[str, dict]],
    elapsed_s: float,
) -> str:
    """Build detailed convergence diagnostics for assertion failures."""
    lines: list[str] = []
    lines.append("Deterministic state convergence check failed")
    lines.append(f"elapsed_s={elapsed_s:.3f}")
    lines.append(f"expected_final_state={json.dumps(expected, sort_keys=True)}")

    for node_id, actual in sorted(actual_by_node.items(), key=lambda kv: kv[0]):
        missing = sorted(set(expected.keys()) - set(actual.keys()))
        extra = sorted(set(actual.keys()) - set(expected.keys()))
        divergent = sorted(
            key
            for key in set(expected.keys()) & set(actual.keys())
            if actual[key] != expected[key]
        )
        lines.append(f"node={node_id} missing_keys={missing} extra_keys={extra} divergent_keys={divergent}")
        lines.append(f"node={node_id} actual_state={json.dumps(actual, sort_keys=True)}")

    return "\n".join(lines)


@pytest.mark.integration
def test_deterministic_state_convergence_real_cluster(
    record_property: pytest.RecordProperty,
) -> None:
    """Assert 6 real nodes converge to expected LWW winning state."""
    cluster_start = time.monotonic()
    nodes = start_cluster(node_count=6)
    try:
        wait_for_readiness(nodes, timeout_s=35.0, interval_s=0.2)

        attached: list[tuple[NodeHandle, FiniteTestSensor]] = []
        for index, node in enumerate(nodes):
            first_unique = attach_finite_sensor(
                node=node,
                sensor_id=f"unique_signal_a_{index}",
                interval_seconds=0.05,
                seed=101 + index,
                max_updates=3,
                unit="itest",
            )
            second_unique = attach_finite_sensor(
                node=node,
                sensor_id=f"unique_signal_b_{index}",
                interval_seconds=0.07,
                seed=201 + index,
                max_updates=2,
                unit="itest",
            )
            attached.append((node, first_unique))
            attached.append((node, second_unique))

        wait_until(
            lambda: all(not sensor.is_running() for _, sensor in attached),
            timeout_s=12.0,
            interval_s=0.05,
            description="all finite deterministic sensors to complete",
        )
        sensors_completed_at = time.monotonic()

        emitted = _collect_emitted_updates(attached)
        expected = _build_expected_winning_state(emitted)
        if not expected:
            raise AssertionError("Expected winning state is empty after sensor completion")

        latest_actual_by_node: dict[str, dict[str, dict]] = {}
        stabilization_timeout_s = 20.0
        convergence_at: float | None = None

        def converged_to_expected() -> bool:
            """Check whether every node has the same state and matches expected winners."""
            nonlocal latest_actual_by_node
            current: dict[str, dict[str, dict]] = {}
            for node in nodes:
                snapshot = fetch_state(node, timeout_s=0.5)
                current[node.node_id] = _extract_node_state(snapshot, node.node_id)

            latest_actual_by_node = current
            states = list(current.values())
            if not states:
                return False
            first = states[0]
            if any(state != first for state in states[1:]):
                return False
            if first != expected:
                return False
            return True

        try:
            wait_until(
                converged_to_expected,
                timeout_s=stabilization_timeout_s,
                interval_s=0.2,
                description="state convergence to expected LWW winners",
            )
            convergence_at = time.monotonic()
        except TimeoutError as exc:
            elapsed_s = time.monotonic() - cluster_start
            diagnostic = _diagnose_state_mismatch(
                expected=expected,
                actual_by_node=latest_actual_by_node,
                elapsed_s=elapsed_s,
            )
            raise AssertionError(f"{exc}\n{diagnostic}") from exc

        injected_updates = len(emitted)
        assert convergence_at is not None
        convergence_wall_clock_s = convergence_at - cluster_start
        stabilization_duration_s = convergence_at - sensors_completed_at
        metrics = {
            "node_count": len(nodes),
            "injected_updates": injected_updates,
            "convergence_wall_clock_s": round(convergence_wall_clock_s, 3),
            "stabilization_duration_s": round(stabilization_duration_s, 3),
            "stabilization_timeout_s": stabilization_timeout_s,
        }
        print(f"CI_METRICS {json.dumps(metrics, sort_keys=True)}", flush=True)
        record_property("node_count", metrics["node_count"])
        record_property("injected_updates", metrics["injected_updates"])
        record_property("convergence_wall_clock_s", metrics["convergence_wall_clock_s"])
        record_property("stabilization_duration_s", metrics["stabilization_duration_s"])
        record_property("stabilization_timeout_s", metrics["stabilization_timeout_s"])
    finally:
        stop_cluster(nodes)
