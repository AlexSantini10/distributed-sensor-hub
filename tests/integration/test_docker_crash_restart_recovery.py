"""Crash/restart Docker recovery test with post-restart reconciliation checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import pytest

from tests.integration.docker_cluster_harness import DockerClusterHarness
from tests.integration.docker_requirements import skip_unless_docker_accessible
from utils.typing import JsonObject


CRASH_COMPOSE = Path("docker/docker-compose-integration-tests.yml")
LOGS_ON_FAILURE = Path("logs/docker-crash-restart-recovery-failure.log")
CRASHED_SERVICE = "node3"
CRASHED_NODE_ID = "node3"


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

    expected: JsonObject = {}
    for sensor_id, winner in winners.items():
        key = f"{winner.origin}:{sensor_id}"
        row: JsonObject = {
            "value": winner.value,
            "ts_ms": winner.ts_ms,
            "origin": winner.origin,
            "meta": winner.meta,
        }
        expected[key] = row
    return dict(sorted(expected.items(), key=lambda kv: kv[0]))


def _state_converged_to_expected(
    harness: DockerClusterHarness,
    *,
    expected: JsonObject,
    node_ids: tuple[str, ...],
    latest_state_sink: dict[str, JsonObject],
) -> bool:
    """Check whether selected nodes converged to one shared expected state."""
    current = {
        node_id: _extract_node_state(harness.fetch_state(node_id, timeout_s=0.8), node_id=node_id)
        for node_id in node_ids
    }
    latest_state_sink.clear()
    latest_state_sink.update(current)
    states = list(current.values())
    if not states:
        return False
    first = states[0]
    if any(state != first for state in states[1:]):
        return False
    return first == expected


def _assert_membership_recovers(harness: DockerClusterHarness, *, restarted_node_id: str) -> bool:
    """Return True when membership snapshots show full peer set and recovered node."""
    expected_peer_count = len(harness.node_ids) - 1
    snapshots = harness.fetch_all_membership(timeout_s=0.8)

    for node_id in harness.node_ids:
        snapshot = snapshots[node_id]
        peers = snapshot.get("peers")
        if not isinstance(peers, list):
            return False
        if len(peers) < expected_peer_count:
            return False

        peer_by_id = {
            peer.get("peer_id"): peer
            for peer in peers
            if isinstance(peer, dict) and isinstance(peer.get("peer_id"), str)
        }
        if set(harness.node_ids) - {node_id} - set(peer_by_id.keys()):
            return False

        if node_id != restarted_node_id:
            restarted_peer = peer_by_id.get(restarted_node_id)
            if not isinstance(restarted_peer, dict):
                return False
            display_status = restarted_peer.get("display_status")
            if display_status not in {"alive_direct", "alive_indirect"}:
                return False

    return True


@pytest.mark.integration
def test_docker_crash_restart_full_sync_recovery() -> None:
    """Assert crash/restart recovery converges state and membership again."""
    skip_unless_docker_accessible()
    harness = DockerClusterHarness(compose_file=CRASH_COMPOSE)

    pre_crash_updates: tuple[_InjectedUpdate, ...] = (
        _InjectedUpdate(
            target_node_id="node1",
            sensor_id="pre_crash_node1@0",
            value=11,
            ts_ms=1700000200000,
            origin="node1",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node2",
            sensor_id="pre_crash_node2@0",
            value=22,
            ts_ms=1700000200100,
            origin="node2",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node3",
            sensor_id="pre_crash_node3@0",
            value=33,
            ts_ms=1700000200200,
            origin="node3",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node4",
            sensor_id="pre_crash_node4@0",
            value=44,
            ts_ms=1700000200300,
            origin="node4",
            meta={"unit": "itest", "period_ms": 25},
        ),
    )
    post_crash_updates: tuple[_InjectedUpdate, ...] = (
        _InjectedUpdate(
            target_node_id="node1",
            sensor_id="post_crash_node1@0",
            value=111,
            ts_ms=1700000201000,
            origin="node1",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node2",
            sensor_id="post_crash_node2@0",
            value=222,
            ts_ms=1700000201100,
            origin="node2",
            meta={"unit": "itest", "period_ms": 25},
        ),
        _InjectedUpdate(
            target_node_id="node4",
            sensor_id="post_crash_node4@0",
            value=444,
            ts_ms=1700000201200,
            origin="node4",
            meta={"unit": "itest", "period_ms": 25},
        ),
    )
    all_updates = (*pre_crash_updates, *post_crash_updates)
    expected = _build_expected_winners(all_updates)

    with harness.running_cluster(
        build=True,
        readiness_timeout_s=60.0,
        dump_logs_on_failure=True,
        failure_logs_file=LOGS_ON_FAILURE,
    ):
        expected_pre_crash = _build_expected_winners(pre_crash_updates)
        pre_crash_state_by_node: dict[str, JsonObject] = {}

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
                for update in pre_crash_updates
            ]
        )

        _wait_until(
            lambda: _state_converged_to_expected(
                harness,
                expected=expected_pre_crash,
                node_ids=harness.node_ids,
                latest_state_sink=pre_crash_state_by_node,
            ),
            timeout_s=20.0,
            interval_s=0.25,
            description="pre-crash state convergence",
        )

        harness.kill_service(CRASHED_SERVICE)

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
                for update in post_crash_updates
            ]
        )

        harness.start_service(CRASHED_SERVICE)
        harness.wait_for_node_readiness(CRASHED_NODE_ID, timeout_s=45.0, interval_s=0.25)

        latest_actual_by_node: dict[str, JsonObject] = {}

        _wait_until(
            lambda: _state_converged_to_expected(
                harness,
                expected=expected,
                node_ids=harness.node_ids,
                latest_state_sink=latest_actual_by_node,
            ),
            timeout_s=35.0,
            interval_s=0.25,
            description="state convergence after crash/restart recovery",
        )

        _wait_until(
            lambda: _assert_membership_recovers(harness, restarted_node_id=CRASHED_NODE_ID),
            timeout_s=35.0,
            interval_s=0.5,
            description="membership recovery after restart",
        )

        assert latest_actual_by_node, "No post-restart snapshots collected"
        final_state = next(iter(latest_actual_by_node.values()))
        assert final_state == expected
        assert set(final_state.keys()) == set(expected.keys())
