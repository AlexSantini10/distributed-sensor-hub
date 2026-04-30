"""Verify end-to-end cluster startup and state replication.

Responsibilities:
    - Poll the HTTP API exposed by Dockerized nodes.
    - Assert that replicated state contains winners from every expected origin.
    - Fail with a bounded timeout when gossip-based convergence does not occur.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from state.state_hash import deterministic_state_hash
from utils.logging import DEMO_LEVEL_NUM, DEMO_LEVEL_NAME, demo_event


RETRYABLE_CLUSTER_ERRORS = (
    AssertionError,
    HTTPError,
    URLError,
    TimeoutError,
    json.JSONDecodeError,
    ConnectionError,
    OSError,
)


def fetch_json(url: str, timeout: float) -> dict:
    """Fetch and decode one JSON document from an HTTP endpoint.

    Args:
        url (str): HTTP endpoint returning a JSON payload.
        timeout (float): Request timeout in seconds.

    Returns:
        dict: Decoded JSON object returned by the endpoint.

    Raises:
        HTTPError: If the endpoint returns an HTTP error status.
        URLError: If the endpoint cannot be reached.
        json.JSONDecodeError: If the payload is not valid JSON.
        OSError: If the underlying socket operation fails.
    """
    with urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def flatten_state(payload: dict) -> dict:
    """Normalize the HTTP state payload into its sensor mapping.

    Args:
        payload (dict): State snapshot grouped by local node identifier.

    Returns:
        dict: Mapping of global sensor identifiers to winning records.

    Raises:
        AssertionError: If the snapshot does not match the expected API contract.
    """
    if not isinstance(payload, dict) or len(payload) != 1:
        raise AssertionError(f"Unexpected state payload shape: {payload!r}")

    _, sensors = next(iter(payload.items()))
    if not isinstance(sensors, dict):
        raise AssertionError(f"Unexpected sensors payload shape: {payload!r}")

    return sensors


def assert_prefixes_present(sensors: dict, required_prefixes: Iterable[str], endpoint: str) -> None:
    """Assert that a snapshot contains replicated winners from all required origins.

    Args:
        sensors (dict): Snapshot mapping keyed by global sensor identifier.
        required_prefixes (Iterable[str]): Origin prefixes expected after convergence.
        endpoint (str): Endpoint label used in assertion failures.

    Returns:
        None: This helper raises when convergence is incomplete.

    Raises:
        AssertionError: If any required origin prefix is absent from the snapshot.
    """
    missing = [
        prefix
        for prefix in required_prefixes
        if not any(sensor_id.startswith(prefix) for sensor_id in sensors)
    ]
    if missing:
        raise AssertionError(
            f"{endpoint} missing replicated data for: {', '.join(missing)}; "
            f"available keys: {sorted(sensors)}"
        )


def wait_for_cluster(endpoints: list[str], required_prefixes: list[str], timeout: float, interval: float) -> None:
    """Poll cluster endpoints until every node exposes all expected origins.

    Args:
        endpoints (list[str]): State endpoints to poll.
        required_prefixes (list[str]): Origin prefixes that must appear on every endpoint.
        timeout (float): Maximum convergence wait in seconds.
        interval (float): Delay between polling rounds in seconds.

    Returns:
        None: This helper returns when the cluster converges.

    Raises:
        SystemExit: If the cluster does not converge before the deadline.
    """
    deadline = time.monotonic() + timeout
    last_error = "cluster did not become ready"

    while time.monotonic() < deadline:
        all_ready = True

        for endpoint in endpoints:
            try:
                state = fetch_json(endpoint, timeout=interval)
                sensors = flatten_state(state)
                assert_prefixes_present(sensors, required_prefixes, endpoint)
            except RETRYABLE_CLUSTER_ERRORS as exc:
                all_ready = False
                last_error = f"{type(exc).__name__}: {exc}"
                break

        if all_ready:
            return

        time.sleep(interval)

    raise SystemExit(last_error)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the cluster verification script.

    Returns:
        argparse.Namespace: Parsed timeout and polling configuration.
    """
    parser = argparse.ArgumentParser(
        description="Verify that the Docker Compose cluster starts and nodes replicate state.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Maximum seconds to wait for full cluster convergence.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the smoke test against the default two-node HTTP endpoints.

    Returns:
        int: Process exit code ``0`` when cluster convergence is verified.

    Raises:
        SystemExit: If the cluster fails to converge before the configured deadline.
    """
    args = parse_args()

    endpoints = [
        "http://127.0.0.1:10000/api/state",
        "http://127.0.0.1:10001/api/state",
    ]
    required_prefixes = ["node-1:", "node-2:"]
    logging.addLevelName(DEMO_LEVEL_NUM, DEMO_LEVEL_NAME)
    logging.basicConfig(level=DEMO_LEVEL_NUM, format="%(message)s")
    log = logging.getLogger("verify_cluster")

    wait_for_cluster(
        endpoints=endpoints,
        required_prefixes=required_prefixes,
        timeout=args.timeout,
        interval=args.interval,
    )
    snapshots = [fetch_json(endpoint, timeout=args.interval) for endpoint in endpoints]
    hashes = {deterministic_state_hash(snapshot) for snapshot in snapshots}
    demo_event(log, "CONVERGENCE", result=("true" if len(hashes) == 1 else "false"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
