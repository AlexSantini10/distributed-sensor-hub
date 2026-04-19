"""Validate the reusable real-cluster integration harness."""

from __future__ import annotations

from tests.integration.cluster_harness import (
    attach_finite_sensor,
    fetch_membership,
    fetch_state,
    start_six_node_cluster,
    stop_cluster,
    wait_for_readiness,
    wait_until,
)

import pytest


@pytest.mark.integration
def test_harness_starts_cluster_and_exposes_state_and_membership() -> None:
    """Assert the harness boots real nodes, attaches sensors, and exposes snapshots."""
    nodes = start_six_node_cluster()
    try:
        wait_for_readiness(nodes, timeout_s=25.0, interval_s=0.2)

        sensors = []
        for index, node in enumerate(nodes):
            sensors.append(
                attach_finite_sensor(
                    node=node,
                    sensor_id=f"deterministic_{index}@0",
                    interval_seconds=0.02,
                    seed=100 + index,
                    max_updates=3,
                    unit="itest",
                )
            )

        wait_until(
            lambda: all(not sensor.is_running() for sensor in sensors),
            timeout_s=5.0,
            interval_s=0.05,
            description="finite sensors to complete",
        )

        node_ids = {node.node_id for node in nodes}

        def all_nodes_expose_all_origins() -> bool:
            for node in nodes:
                state = fetch_state(node, timeout_s=0.5)
                per_node = state.get(node.node_id)
                if not isinstance(per_node, dict):
                    return False

                observed_origins = {
                    key.split(":", 1)[0]
                    for key in per_node.keys()
                    if ":" in key
                }
                if not node_ids.issubset(observed_origins):
                    return False
            return True

        wait_until(
            all_nodes_expose_all_origins,
            timeout_s=12.0,
            interval_s=0.2,
            description="state convergence across origins",
        )

        for node in nodes:
            membership = fetch_membership(node, timeout_s=0.5)
            peers = membership.get("peers")
            assert isinstance(peers, list)
            assert len(peers) >= 5
    finally:
        stop_cluster(nodes)
