"""Smoke test for the Dockerized two-node cluster."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def fetch_json(url: str, timeout: float) -> dict:
	with urlopen(url, timeout=timeout) as response:
		payload = response.read().decode("utf-8")
	return json.loads(payload)


def flatten_state(payload: dict) -> dict:
	if not isinstance(payload, dict) or len(payload) != 1:
		raise AssertionError(f"Unexpected state payload shape: {payload!r}")

	_, sensors = next(iter(payload.items()))
	if not isinstance(sensors, dict):
		raise AssertionError(f"Unexpected sensors payload shape: {payload!r}")

	return sensors


def assert_prefixes_present(sensors: dict, required_prefixes: Iterable[str], endpoint: str) -> None:
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
	deadline = time.monotonic() + timeout
	last_error = "cluster did not become ready"

	while time.monotonic() < deadline:
		all_ready = True

		for endpoint in endpoints:
			try:
				state = fetch_json(endpoint, timeout=interval)
				sensors = flatten_state(state)
				assert_prefixes_present(sensors, required_prefixes, endpoint)
			except (AssertionError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
				all_ready = False
				last_error = f"{type(exc).__name__}: {exc}"
				break

		if all_ready:
			return

		time.sleep(interval)

	raise SystemExit(last_error)


def parse_args() -> argparse.Namespace:
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
	args = parse_args()

	endpoints = [
		"http://127.0.0.1:10000/api/state",
		"http://127.0.0.1:10001/api/state",
	]
	required_prefixes = ["node-1:", "node-2:"]

	wait_for_cluster(
		endpoints=endpoints,
		required_prefixes=required_prefixes,
		timeout=args.timeout,
		interval=args.interval,
	)

	print("Cluster startup and node replication verified.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
