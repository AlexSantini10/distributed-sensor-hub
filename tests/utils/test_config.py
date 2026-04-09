"""Validate environment-driven configuration parsing.

Responsibilities:
    - Assert successful config loading from required variables.
    - Reject missing or malformed environment input deterministically.
"""

import os

import pytest
from pytest import MonkeyPatch

from utils.config import Config, LogLevel, _parse_peers


def _set_base_env(monkeypatch: MonkeyPatch) -> None:
    """Populate the minimum environment required for config loading.

    Args:
        monkeypatch (MonkeyPatch): Pytest monkeypatch fixture used to set environment variables.

    Returns:
        None: This helper mutates the process environment for the current test.
    """
    monkeypatch.setenv("NODE_ID", "node-1")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "logs/test.log")


def test_load_config_success(monkeypatch: MonkeyPatch) -> None:
    """Assert that valid environment variables produce the expected config object.

    Args:
        monkeypatch (MonkeyPatch): Pytest monkeypatch fixture used to set environment variables.

    Returns:
        None: This test asserts successful parsing.
    """
    _set_base_env(monkeypatch)
    monkeypatch.setenv(
        "BOOTSTRAP_PEERS",
        "127.0.0.1:9001,127.0.0.1:9002",
    )

    config = Config.from_env(dict(os.environ))

    assert config.node_id == "node-1"
    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.bootstrap_peers == (
        ("127.0.0.1", 9001),
        ("127.0.0.1", 9002),
    )
    assert config.log_level == LogLevel.INFO
    assert config.log_level_name == "INFO"
    assert config.log_file == "logs/test.log"
    assert config.web_api_port == 10000
    assert config.heartbeat_interval_ms == 1000
    assert config.replication_delta_maxlen == 512
    assert config.sensors == ()


def test_missing_required_env(monkeypatch: MonkeyPatch) -> None:
    """Assert that missing required variables abort config loading.

    Args:
        monkeypatch (MonkeyPatch): Pytest monkeypatch fixture used to remove environment variables.

    Returns:
        None: This test asserts validation failure.
    """
    _set_base_env(monkeypatch)
    monkeypatch.delenv("NODE_ID")

    with pytest.raises(RuntimeError):
        Config.from_env(dict(os.environ))


def test_empty_bootstrap_peers(monkeypatch: MonkeyPatch) -> None:
    """Assert that an empty peer list is accepted as no bootstrap peers.

    Args:
        monkeypatch (MonkeyPatch): Pytest monkeypatch fixture used to set environment variables.

    Returns:
        None: This test asserts optional peer-list handling.
    """
    _set_base_env(monkeypatch)
    monkeypatch.setenv("BOOTSTRAP_PEERS", "")

    config = Config.from_env(dict(os.environ))
    assert config.bootstrap_peers == ()


def test_invalid_peer_format() -> None:
    """Assert that malformed ``host:port`` entries are rejected.

    Returns:
        None: This test asserts peer-list validation.
    """
    with pytest.raises(RuntimeError):
        _parse_peers("127.0.0.1")
