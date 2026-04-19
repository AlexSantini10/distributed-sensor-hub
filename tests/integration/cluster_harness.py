"""Reusable real-cluster harness for deterministic integration tests.

Responsibilities:
    - Allocate ephemeral ports for test nodes.
    - Start and stop real ``NodeApplication`` instances.
    - Provide polling/deadline utilities for readiness and assertions.
    - Expose HTTP helpers for ``/api/state`` and ``/api/membership``.
    - Attach finite test sensors via the normal runtime ingestion path.
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import json

from runtime.application import NodeApplication
from tests.integration.finite_test_sensor import FiniteTestSensor
from utils.config import Config
from utils.typing import JsonObject


RETRYABLE_HTTP_ERRORS = (
    TimeoutError,
    OSError,
    ConnectionError,
    URLError,
    HTTPError,
    json.JSONDecodeError,
)


def allocate_free_port(*, host: str = "127.0.0.1") -> int:
    """Allocate one ephemeral TCP port.

    Args:
        host (str): Host/interface used for ephemeral bind.

    Returns:
        int: Ephemeral port selected by the OS.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def allocate_node_ports(
    *,
    node_count: int,
    host: str = "127.0.0.1",
) -> list[tuple[int, int]]:
    """Allocate ``(p2p_port, web_api_port)`` pairs for test nodes."""
    pairs: list[tuple[int, int]] = []
    for _ in range(node_count):
        p2p_port = allocate_free_port(host=host)
        web_api_port = allocate_free_port(host=host)
        pairs.append((p2p_port, web_api_port))
    return pairs


def poll_until(
    condition: Callable[[], bool],
    *,
    timeout_s: float,
    interval_s: float = 0.1,
    description: str = "condition",
) -> None:
    """Poll until ``condition`` succeeds or timeout elapses.

    Raises:
        TimeoutError: If condition does not become true before the deadline.
    """
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except Exception as exc:  # pragma: no cover - timeout path diagnostics
            last_error = exc
        time.sleep(interval_s)

    if last_error is None:
        raise TimeoutError(f"Timed out waiting for {description}")
    raise TimeoutError(f"Timed out waiting for {description}: {type(last_error).__name__}: {last_error}")


def fetch_json(url: str, *, timeout_s: float = 1.0) -> JsonObject:
    """Fetch one JSON payload from an HTTP endpoint."""
    with urlopen(url, timeout=timeout_s) as response:
        payload = response.read().decode("utf-8")
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise TypeError(f"Expected JSON object from {url}, got {type(decoded).__name__}")
    return decoded


def _make_test_logger(name: str) -> logging.Logger:
    """Build a logger suitable for multithreaded integration harness runs."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def _build_test_config(
    *,
    node_id: str,
    host: str,
    port: int,
    web_api_port: int,
    bootstrap_peers: tuple[tuple[str, int], ...],
) -> Config:
    """Build a minimal runtime ``Config`` for integration harness nodes."""
    return Config.from_env(
        {
            "NODE_ID": node_id,
            "HOST": host,
            "PORT": str(port),
            "BOOTSTRAP_PEERS": ",".join(f"{peer_host}:{peer_port}" for peer_host, peer_port in bootstrap_peers),
            "LOG_LEVEL": "INFO",
            "LOG_FILE": f"logs/{node_id}-integration.log",
            "CLEAR_LOG": "false",
            "WEB_API_PORT": str(web_api_port),
            "SENSORS": "0",
            "HEARTBEAT_INTERVAL_MS": "400",
            "GOSSIP_SYNC_INTERVAL_MS": "300",
            "GOSSIP_PUSH_RATIO": "1.0",
            "GOSSIP_PUSH_MIN_PEERS": "1",
            "GOSSIP_PULL_RATIO": "1.0",
            "GOSSIP_PULL_MIN_PEERS": "1",
            "GOSSIP_PULL_EVERY_ROUNDS": "1",
            "NETWORK_DELAY_MS": "0",
            "NETWORK_DELAY_JITTER_MS": "0",
            "NETWORK_DELAY_SPIKE_PROB": "0",
            "NETWORK_DELAY_SPIKE_MS": "0",
            "NETWORK_PACKET_LOSS_PROB": "0",
        }
    )


@dataclass(frozen=True)
class NodeHandle:
    """Runtime metadata and helpers for one started test node."""

    node_id: str
    host: str
    p2p_port: int
    web_api_port: int
    app: NodeApplication

    @property
    def state_url(self) -> str:
        return f"http://{self.host}:{self.web_api_port}/api/state"

    @property
    def membership_url(self) -> str:
        return f"http://{self.host}:{self.web_api_port}/api/membership"

    def fetch_state(self, *, timeout_s: float = 1.0) -> JsonObject:
        """Fetch ``/api/state`` snapshot for this node."""
        return fetch_json(self.state_url, timeout_s=timeout_s)

    def fetch_membership(self, *, timeout_s: float = 1.0) -> JsonObject:
        """Fetch ``/api/membership`` snapshot for this node."""
        return fetch_json(self.membership_url, timeout_s=timeout_s)


def start_cluster(*, node_count: int = 6, host: str = "127.0.0.1") -> list[NodeHandle]:
    """Start a real cluster using runtime startup code.

    Topology:
        - node-1 has no bootstrap peers.
        - every other node bootstraps via node-1.

    Args:
        node_count (int): Number of nodes to start. Must be >= 2.
        host (str): Host used for all test node binds.

    Returns:
        list[NodeHandle]: Started node handles in startup order.
    """
    if node_count < 2:
        raise ValueError("node_count must be >= 2")

    node_ids = tuple(f"node-{index}" for index in range(1, node_count + 1))
    ports = allocate_node_ports(node_count=node_count, host=host)

    config_by_id: dict[str, Config] = {}
    node1_port = ports[0][0]
    for index, node_id in enumerate(node_ids):
        p2p_port, web_api_port = ports[index]
        bootstrap = () if node_id == "node-1" else ((host, node1_port),)
        config_by_id[node_id] = _build_test_config(
            node_id=node_id,
            host=host,
            port=p2p_port,
            web_api_port=web_api_port,
            bootstrap_peers=bootstrap,
        )

    started: list[NodeHandle] = []
    try:
        for node_id in node_ids:
            config = config_by_id[node_id]
            app = NodeApplication(
                config=config,
                log=_make_test_logger(f"tests.integration.cluster.{node_id}"),
            )
            app.start()
            started.append(
                NodeHandle(
                    node_id=node_id,
                    host=host,
                    p2p_port=config.port,
                    web_api_port=config.web_api_port,
                    app=app,
                )
            )
    except Exception:
        stop_cluster(started)
        raise

    return started


def start_three_node_cluster(*, host: str = "127.0.0.1") -> list[NodeHandle]:
    """Start a real 3-node cluster (compatibility helper)."""
    return start_cluster(node_count=3, host=host)


def start_six_node_cluster(*, host: str = "127.0.0.1") -> list[NodeHandle]:
    """Start a real 6-node cluster."""
    return start_cluster(node_count=6, host=host)


def stop_cluster(nodes: list[NodeHandle]) -> None:
    """Stop all nodes in reverse startup order."""
    for node in reversed(nodes):
        try:
            node.app.stop()
        except Exception:
            continue


def wait_for_readiness(
    nodes: list[NodeHandle],
    *,
    timeout_s: float = 20.0,
    interval_s: float = 0.1,
) -> None:
    """Wait until every node serves ``/api/state`` successfully."""
    node_ids = tuple(node.node_id for node in nodes)

    def all_state_endpoints_ready() -> bool:
        for node in nodes:
            snapshot = node.fetch_state(timeout_s=interval_s)
            if node.node_id not in snapshot:
                raise AssertionError(
                    f"{node.node_id} state snapshot missing root key {node.node_id}: {snapshot}"
                )
        return True

    poll_until(
        all_state_endpoints_ready,
        timeout_s=timeout_s,
        interval_s=interval_s,
        description=f"cluster readiness for nodes={node_ids}",
    )


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout_s: float,
    interval_s: float = 0.1,
    description: str = "condition",
) -> None:
    """Alias used by integration tests for generic deadline polling."""
    poll_until(
        condition,
        timeout_s=timeout_s,
        interval_s=interval_s,
        description=description,
    )


def attach_finite_sensor(
    *,
    node: NodeHandle,
    sensor_id: str,
    interval_seconds: float,
    seed: int,
    max_updates: int | None = None,
    duration_seconds: float | None = None,
    unit: str | None = None,
    start_immediately: bool = True,
) -> FiniteTestSensor:
    """Register and optionally start a finite deterministic sensor on a node."""
    sensor = FiniteTestSensor(
        sensor_id=sensor_id,
        interval_seconds=interval_seconds,
        seed=seed,
        max_updates=max_updates,
        duration_seconds=duration_seconds,
        unit=unit,
    )
    manager = node.app.sensor_manager
    if manager is None:
        raise RuntimeError(f"Sensor manager is not available for node {node.node_id}")

    manager.register(sensor)
    if start_immediately:
        sensor.start()
    return sensor


def fetch_state(node: NodeHandle, *, timeout_s: float = 1.0) -> JsonObject:
    """Helper to fetch ``/api/state`` from a node handle."""
    return node.fetch_state(timeout_s=timeout_s)


def fetch_membership(node: NodeHandle, *, timeout_s: float = 1.0) -> JsonObject:
    """Helper to fetch ``/api/membership`` from a node handle."""
    return node.fetch_membership(timeout_s=timeout_s)
