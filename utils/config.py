import os
from dataclasses import dataclass
from typing import List, Tuple


_ALLOWED_LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise RuntimeError(f"PORT must be an integer, got: {raw}")

    if not (0 < port < 65536):
        raise RuntimeError(f"Invalid PORT value: {port}")

    return port


def _parse_peers(raw: str) -> List[Tuple[str, int]]:
    if raw.strip() == "":
        return []

    peers: List[Tuple[str, int]] = []

    for item in raw.split(","):
        item = item.strip()
        try:
            host, port = item.split(":")
            peers.append((host.strip(), _parse_port(port)))
        except ValueError:
            raise RuntimeError(
                f"Invalid peer format: {item} (expected host:port)"
            )

    return peers


@dataclass(frozen=True)
class Config:
    node_id: str
    host: str
    port: int
    bootstrap_peers: List[Tuple[str, int]]
    log_level: str
    log_file: str


def load_config() -> Config:
    node_id = _require_env("NODE_ID")
    host = _require_env("HOST")
    port = _parse_port(_require_env("PORT"))

    log_level = _require_env("LOG_LEVEL").upper()
    if log_level not in _ALLOWED_LOG_LEVELS:
        raise RuntimeError(
            f"Invalid LOG_LEVEL: {log_level} "
            f"(allowed: {', '.join(sorted(_ALLOWED_LOG_LEVELS))})"
        )

    log_file = _require_env("LOG_FILE")

    raw_peers = os.getenv("BOOTSTRAP_PEERS", "")
    bootstrap_peers = _parse_peers(raw_peers)

    return Config(
        node_id=node_id,
        host=host,
        port=port,
        bootstrap_peers=bootstrap_peers,
        log_level=log_level,
        log_file=log_file,
    )
