"""Reusable Docker harness for real-container integration tests.

Responsibilities:
    - Start and stop a dedicated Docker Compose topology for integration tests.
    - Poll node readiness and fetch `/api/state` and `/api/membership` snapshots.
    - Inject deterministic bounded updates through the real framed TCP protocol.
    - Perform Docker-level partition/heal operations by network disconnect/connect.
    - Dump compose logs on failures for CI diagnostics.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from protocol.factory import build_sensor_update
from protocol.messages import SensorMeta
from utils.typing import JsonObject


RETRYABLE_HTTP_ERRORS = (
    TimeoutError,
    OSError,
    ConnectionError,
    URLError,
    HTTPError,
    json.JSONDecodeError,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_COMPOSE_FILE = ROOT_DIR / "docker" / "docker-compose-integration-tests.yml"


class DockerHarnessError(RuntimeError):
    """Raised when compose/network orchestration fails."""


@dataclass(frozen=True)
class NodeSpec:
    """Static test-topology metadata for one node."""

    node_id: str
    service: str
    p2p_port: int
    web_api_port: int
    subgroup: str

    @property
    def state_url(self) -> str:
        """Return the node's `/api/state` URL on localhost."""
        return f"http://127.0.0.1:{self.web_api_port}/api/state"

    @property
    def membership_url(self) -> str:
        """Return the node's `/api/membership` URL on localhost."""
        return f"http://127.0.0.1:{self.web_api_port}/api/membership"


DEFAULT_NODE_SPECS: tuple[NodeSpec, ...] = (
    NodeSpec(node_id="node1", service="node1", p2p_port=9100, web_api_port=11000, subgroup="a"),
    NodeSpec(node_id="node2", service="node2", p2p_port=9101, web_api_port=11001, subgroup="a"),
    NodeSpec(node_id="node3", service="node3", p2p_port=9102, web_api_port=11002, subgroup="b"),
    NodeSpec(node_id="node4", service="node4", p2p_port=9103, web_api_port=11003, subgroup="b"),
)


def _fetch_json(url: str, *, timeout_s: float) -> JsonObject:
    """Fetch and decode one JSON object from an HTTP endpoint."""
    with urlopen(url, timeout=timeout_s) as response:
        payload = response.read().decode("utf-8")
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise TypeError(f"Expected object payload from {url}, got {type(decoded).__name__}")
    return decoded


def _require_file(path: Path) -> Path:
    """Validate that a path exists and return its absolute form."""
    resolved = path.resolve()
    if not resolved.exists():
        raise DockerHarnessError(f"File not found: {resolved}")
    return resolved


class DockerClusterHarness:
    """Lifecycle and orchestration API for Docker-backed integration tests."""

    def __init__(
        self,
        *,
        compose_file: Path | str = DEFAULT_COMPOSE_FILE,
        node_specs: tuple[NodeSpec, ...] = DEFAULT_NODE_SPECS,
        project_name: str | None = None,
    ) -> None:
        """Create a harness bound to one compose file and project name."""
        self.compose_file = _require_file(Path(compose_file))
        self.node_specs = node_specs
        self.project_name = project_name or f"dsh-itest-{os.getpid()}-{int(time.time())}"
        self._started = False

        self._spec_by_id = {spec.node_id: spec for spec in self.node_specs}
        self._spec_by_service = {spec.service: spec for spec in self.node_specs}

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Return ordered node IDs in the configured topology."""
        return tuple(spec.node_id for spec in self.node_specs)

    @property
    def subgroup_a_node_ids(self) -> tuple[str, ...]:
        """Return node IDs in subgroup A."""
        return tuple(spec.node_id for spec in self.node_specs if spec.subgroup == "a")

    @property
    def subgroup_b_node_ids(self) -> tuple[str, ...]:
        """Return node IDs in subgroup B."""
        return tuple(spec.node_id for spec in self.node_specs if spec.subgroup == "b")

    def start(self, *, build: bool = True) -> None:
        """Start the compose cluster in detached mode."""
        args = ["up"]
        if build:
            args.append("--build")
        args.extend(["-d", "--remove-orphans"])
        self._run_compose(args)
        self._started = True

    def stop(self, *, remove_volumes: bool = True) -> None:
        """Stop and remove compose resources."""
        args = ["down", "--remove-orphans"]
        if remove_volumes:
            args.append("--volumes")
        self._run_compose(args, check=False)
        self._started = False

    def wait_for_readiness(
        self,
        *,
        timeout_s: float = 45.0,
        interval_s: float = 0.2,
    ) -> None:
        """Wait until every node exposes a valid `/api/state` snapshot."""
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                for spec in self.node_specs:
                    snapshot = _fetch_json(spec.state_url, timeout_s=interval_s)
                    if spec.node_id not in snapshot:
                        raise AssertionError(
                            f"{spec.node_id} state snapshot missing root key {spec.node_id}: {snapshot}"
                        )
                return
            except Exception as exc:  # pragma: no cover - diagnostics path
                last_error = exc
                time.sleep(interval_s)

        if last_error is None:
            raise TimeoutError("Timed out waiting for Docker cluster readiness")
        raise TimeoutError(
            "Timed out waiting for Docker cluster readiness: "
            f"{type(last_error).__name__}: {last_error}"
        )

    def wait_for_node_readiness(
        self,
        node_id: str,
        *,
        timeout_s: float = 45.0,
        interval_s: float = 0.2,
    ) -> None:
        """Wait until one node exposes a valid `/api/state` snapshot."""
        spec = self._resolve_node(node_id)
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            try:
                snapshot = _fetch_json(spec.state_url, timeout_s=interval_s)
                if spec.node_id not in snapshot:
                    raise AssertionError(
                        f"{spec.node_id} state snapshot missing root key {spec.node_id}: {snapshot}"
                    )
                return
            except Exception as exc:  # pragma: no cover - diagnostics path
                last_error = exc
                time.sleep(interval_s)

        if last_error is None:
            raise TimeoutError(f"Timed out waiting for node readiness node_id={node_id}")
        raise TimeoutError(
            f"Timed out waiting for node readiness node_id={node_id}: "
            f"{type(last_error).__name__}: {last_error}"
        )

    def fetch_state(self, node_id: str, *, timeout_s: float = 1.0) -> JsonObject:
        """Fetch one node `/api/state` payload."""
        spec = self._resolve_node(node_id)
        return _fetch_json(spec.state_url, timeout_s=timeout_s)

    def fetch_membership(self, node_id: str, *, timeout_s: float = 1.0) -> JsonObject:
        """Fetch one node `/api/membership` payload."""
        spec = self._resolve_node(node_id)
        return _fetch_json(spec.membership_url, timeout_s=timeout_s)

    def fetch_all_states(self, *, timeout_s: float = 1.0) -> dict[str, JsonObject]:
        """Fetch `/api/state` payloads for all nodes."""
        return {
            spec.node_id: _fetch_json(spec.state_url, timeout_s=timeout_s)
            for spec in self.node_specs
        }

    def fetch_all_membership(self, *, timeout_s: float = 1.0) -> dict[str, JsonObject]:
        """Fetch `/api/membership` payloads for all nodes."""
        return {
            spec.node_id: _fetch_json(spec.membership_url, timeout_s=timeout_s)
            for spec in self.node_specs
        }

    def inject_sensor_update(
        self,
        *,
        target_node_id: str,
        sensor_id: str,
        value: object,
        ts_ms: int,
        origin: str | None = None,
        meta: JsonObject | None = None,
        sender_id: str = "integration-injector",
        envelope_ts_ms: int | None = None,
        timeout_s: float = 1.0,
    ) -> None:
        """Inject one `SENSOR_UPDATE` frame directly into a node TCP endpoint.

        By default `origin` is set to `target_node_id` so the receiving node can
        republish the winning update during gossip rounds.
        """
        spec = self._resolve_node(target_node_id)
        effective_origin = target_node_id if origin is None else origin

        msg = build_sensor_update(
            sender_id=sender_id,
            sensor_id=sensor_id,
            value=value,
            ts_ms=ts_ms,
            origin=effective_origin,
            meta=SensorMeta.from_mapping(meta or {}),
            timestamp=envelope_ts_ms,
        )
        payload = msg.to_bytes()
        frame = struct.pack(">I", len(payload)) + payload

        with socket.create_connection(("127.0.0.1", spec.p2p_port), timeout=timeout_s) as sock:
            sock.sendall(frame)

    def inject_sensor_updates(self, updates: list[JsonObject]) -> None:
        """Inject multiple deterministic updates in order."""
        for update in updates:
            target_node_id = update.get("target_node_id")
            sensor_id = update.get("sensor_id")
            ts_ms = update.get("ts_ms")
            if not isinstance(target_node_id, str):
                raise TypeError("update.target_node_id must be a string")
            if not isinstance(sensor_id, str):
                raise TypeError("update.sensor_id must be a string")
            if not isinstance(ts_ms, int):
                raise TypeError("update.ts_ms must be an int")

            self.inject_sensor_update(
                target_node_id=target_node_id,
                sensor_id=sensor_id,
                value=update.get("value"),
                ts_ms=ts_ms,
                origin=update.get("origin") if isinstance(update.get("origin"), str) else None,
                meta=update.get("meta") if isinstance(update.get("meta"), dict) else None,
                sender_id=(
                    update.get("sender_id")
                    if isinstance(update.get("sender_id"), str)
                    else "integration-injector"
                ),
                envelope_ts_ms=(
                    update.get("envelope_ts_ms")
                    if isinstance(update.get("envelope_ts_ms"), int)
                    else None
                ),
            )

    def partition_subgroups(self) -> None:
        """Partition A/B by disconnecting all containers from the shared network."""
        shared_network = self._resolve_network_name("shared")
        for spec in self.node_specs:
            container_id = self._resolve_container_id(spec.service)
            self._docker_network_disconnect(
                network_name=shared_network,
                container_id=container_id,
            )

    def heal_subgroups(self) -> None:
        """Heal A/B partition by reconnecting all containers to shared network."""
        shared_network = self._resolve_network_name("shared")
        for spec in self.node_specs:
            container_id = self._resolve_container_id(spec.service)
            self._docker_network_connect(
                network_name=shared_network,
                container_id=container_id,
            )

    def kill_service(self, service: str, *, signal: str = "SIGKILL") -> None:
        """Abruptly kill one compose service container."""
        self._run_compose(["kill", "-s", signal, service])

    def start_service(self, service: str) -> None:
        """Start one stopped/killed compose service container."""
        self._run_compose(["start", service])

    def restart_service(self, service: str) -> None:
        """Restart one compose service container."""
        self._run_compose(["restart", service])

    def dump_compose_logs(self, *, output_file: Path | str | None = None) -> str:
        """Return compose logs and optionally persist them to a file."""
        result = self._run_compose(["logs", "--no-color"], check=False, capture_output=True)
        logs = result.stdout
        if output_file is not None:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(logs, encoding="utf-8")
        return logs

    @contextmanager
    def running_cluster(
        self,
        *,
        build: bool = True,
        readiness_timeout_s: float = 45.0,
        dump_logs_on_failure: bool = True,
        failure_logs_file: Path | str | None = None,
    ):
        """Context manager that ensures start/readiness/teardown and failure logs."""
        self.start(build=build)
        try:
            self.wait_for_readiness(timeout_s=readiness_timeout_s)
            yield self
        except Exception:
            if dump_logs_on_failure:
                self.dump_compose_logs(output_file=failure_logs_file)
            raise
        finally:
            self.stop(remove_volumes=True)

    def _resolve_node(self, node_id: str) -> NodeSpec:
        """Resolve one configured node by id."""
        spec = self._spec_by_id.get(node_id)
        if spec is None:
            raise KeyError(f"Unknown node_id: {node_id}")
        return spec

    def _compose_base_command(self) -> list[str]:
        """Build the command prefix for compose invocations."""
        return [
            "docker",
            "compose",
            "-f",
            str(self.compose_file),
            "-p",
            self.project_name,
        ]

    def _run_compose(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run one docker compose command and return subprocess metadata."""
        cmd = [*self._compose_base_command(), *args]
        return self._run_command(cmd, check=check, capture_output=capture_output)

    def _run_docker(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Run one docker command and return subprocess metadata."""
        cmd = ["docker", *args]
        return self._run_command(cmd, check=check, capture_output=capture_output)

    def _run_command(
        self,
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        """Run one command with text output and wrapped error reporting."""
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            check=False,
            text=True,
            capture_output=capture_output,
        )
        if check and result.returncode != 0:
            raise DockerHarnessError(
                f"Command failed: {' '.join(cmd)}\n"
                f"exit_code={result.returncode}\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            )
        return result

    def _resolve_container_id(self, service: str) -> str:
        """Resolve container ID for a compose service."""
        result = self._run_compose(["ps", "-q", service], capture_output=True)
        container_id = result.stdout.strip()
        if container_id == "":
            raise DockerHarnessError(
                f"Could not resolve container id for service={service} project={self.project_name}"
            )
        return container_id

    def _resolve_network_name(self, compose_network: str) -> str:
        """Resolve concrete Docker network name from compose project labels."""
        result = self._run_docker(
            [
                "network",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={self.project_name}",
                "--filter",
                f"label=com.docker.compose.network={compose_network}",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise DockerHarnessError(
                f"Could not resolve network compose_name={compose_network} project={self.project_name}"
            )
        return lines[0]

    def _docker_network_disconnect(self, *, network_name: str, container_id: str) -> None:
        """Disconnect container from network, ignoring already-disconnected cases."""
        result = self._run_docker(
            ["network", "disconnect", network_name, container_id],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
        stderr = (result.stderr or "").lower()
        if "is not connected to network" in stderr:
            return
        raise DockerHarnessError(
            f"Failed network disconnect network={network_name} container={container_id}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

    def _docker_network_connect(self, *, network_name: str, container_id: str) -> None:
        """Connect container to network, ignoring already-connected cases."""
        result = self._run_docker(
            ["network", "connect", network_name, container_id],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
        stderr = (result.stderr or "").lower()
        if "already exists in network" in stderr:
            return
        raise DockerHarnessError(
            f"Failed network connect network={network_name} container={container_id}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
