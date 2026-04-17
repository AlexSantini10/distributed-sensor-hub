"""Validate environment-driven configuration parsing.

Responsibilities:
    - Assert successful config loading from required variables.
    - Reject missing or malformed environment input deterministically.
"""

import os

import pytest
from pytest import MonkeyPatch

from utils.config import Config, LogLevel, TopologyPolicyName, _parse_peers


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
    assert config.gossip_sync_interval_ms == 1000
    assert config.gossip_push_ratio == 0.3
    assert config.gossip_push_min_peers == 2
    assert config.gossip_pull_ratio == 0.15
    assert config.gossip_pull_min_peers == 1
    assert config.gossip_pull_every_rounds == 3
    assert config.phi_threshold_suspect == 3.0
    assert config.phi_threshold_dead == 8.0
    assert config.phi_initial_interval_s == 1.0
    assert config.replication_delta_maxlen == 512
    assert config.network_delay_ms == 0.0
    assert config.network_delay_jitter_ms == 0.0
    assert config.network_delay_spike_prob == 0.0
    assert config.network_delay_spike_ms == 0.0
    assert config.network_packet_loss_prob == 0.0
    assert config.topology_policy is TopologyPolicyName.FULL_MESH
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


def test_invalid_packet_loss_probability(monkeypatch: MonkeyPatch) -> None:
    """Assert that network probabilities above 1 are rejected."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("NETWORK_PACKET_LOSS_PROB", "1.2")

    with pytest.raises(RuntimeError):
        Config.from_env(dict(os.environ))


def test_invalid_phi_threshold_order(monkeypatch: MonkeyPatch) -> None:
    """Assert dead threshold cannot be smaller than suspect threshold."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("PHI_THRESHOLD_SUSPECT", "4.0")
    monkeypatch.setenv("PHI_THRESHOLD_DEAD", "3.0")

    with pytest.raises(RuntimeError):
        Config.from_env(dict(os.environ))


def test_invalid_topology_policy(monkeypatch: MonkeyPatch) -> None:
    """Assert unknown topology policy names are rejected."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TOPOLOGY_POLICY", "unknown")

    with pytest.raises(RuntimeError):
        Config.from_env(dict(os.environ))


def test_invalid_gossip_push_ratio(monkeypatch: MonkeyPatch) -> None:
    """Assert gossip push ratio must stay within the closed interval [0, 1]."""
    _set_base_env(monkeypatch)
    monkeypatch.setenv("GOSSIP_PUSH_RATIO", "1.4")

    with pytest.raises(RuntimeError):
        Config.from_env(dict(os.environ))
