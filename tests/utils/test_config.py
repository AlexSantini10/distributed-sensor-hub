import pytest
from utils.config import load_config, _parse_peers


def _set_base_env(monkeypatch):
    monkeypatch.setenv("NODE_ID", "node-1")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "logs/test.log")


def test_load_config_success(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv(
        "BOOTSTRAP_PEERS",
        "127.0.0.1:9001,127.0.0.1:9002",
    )

    config = load_config()

    assert config.node_id == "node-1"
    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.bootstrap_peers == [
        ("127.0.0.1", 9001),
        ("127.0.0.1", 9002),
    ]
    assert config.log_level == "INFO"
    assert config.log_file == "logs/test.log"


def test_missing_required_env(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.delenv("NODE_ID")

    with pytest.raises(RuntimeError):
        load_config()


def test_empty_bootstrap_peers(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("BOOTSTRAP_PEERS", "")

    config = load_config()
    assert config.bootstrap_peers == []


def test_invalid_peer_format():
    with pytest.raises(RuntimeError):
        _parse_peers("127.0.0.1")
