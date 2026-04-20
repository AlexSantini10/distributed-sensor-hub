"""Docker availability helpers for Docker-backed integration tests."""

from __future__ import annotations

from functools import lru_cache
import subprocess

import pytest


@lru_cache(maxsize=1)
def docker_unavailable_reason() -> str | None:
    """Return a skip reason when Docker is unavailable for integration tests."""
    probe = subprocess.run(
        ["docker", "info"],
        check=False,
        text=True,
        capture_output=True,
    )
    if probe.returncode == 0:
        return None

    stderr = (probe.stderr or "").strip()
    stdout = (probe.stdout or "").strip()
    details = stderr if stderr != "" else stdout
    if details == "":
        details = "docker info returned a non-zero exit code"
    return f"Docker unavailable for integration test execution: {details}"


def skip_unless_docker_accessible() -> None:
    """Skip current test when Docker is not reachable by the current user."""
    reason = docker_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)
