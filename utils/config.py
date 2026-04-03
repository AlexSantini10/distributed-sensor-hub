"""Load validated runtime configuration from environment variables.

Responsibilities:
    - Enforce required configuration keys for node startup.
    - Parse ports and bootstrap peer lists into typed runtime values.
    - Reject invalid configuration before networking or state services start.
"""

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
    """Read one required environment variable.

    Args:
        name (str): Environment-variable name that must be defined and non-empty.

    Returns:
        str: Stripped environment-variable value.

    Raises:
        RuntimeError: If the variable is missing or resolves to blank text.
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _parse_port(raw: str) -> int:
    """Parse one TCP port value from text.

    Args:
        raw (str): Raw port string read from the environment.

    Returns:
        int: Valid TCP port number.

    Raises:
        RuntimeError: If the value is not an integer in the valid TCP port range.
    """
    try:
        port = int(raw)
    except ValueError:
        raise RuntimeError(f"PORT must be an integer, got: {raw}")

    if not (0 < port < 65536):
        raise RuntimeError(f"Invalid PORT value: {port}")

    return port


def _parse_peers(raw: str) -> List[Tuple[str, int]]:
    """Parse bootstrap peers from a comma-separated ``host:port`` list.

    Args:
        raw (str): Raw peer list from the environment.

    Returns:
        List[Tuple[str, int]]: Ordered bootstrap peers for initial membership joins.

    Raises:
        RuntimeError: If any peer entry does not follow the expected ``host:port`` format.
    """
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
    """Bundle validated node startup configuration.

    Attributes:
        node_id (str): Stable node identifier advertised to peers and used in LWW ties.
        host (str): Interface address used for the node's TCP server bind.
        port (int): TCP server port exposed by the node.
        bootstrap_peers (List[Tuple[str, int]]): Initial peers contacted for cluster join.
        log_level (str): Root logging level applied during runtime startup.
        log_file (str): Path to the process log file.
    """

    node_id: str
    host: str
    port: int
    bootstrap_peers: List[Tuple[str, int]]
    log_level: str
    log_file: str


def load_config() -> Config:
    """Load and validate the process configuration from environment variables.

    Returns:
        Config: Immutable runtime configuration for node bootstrap.

    Raises:
        RuntimeError: If any required variable is missing or invalid.
    """
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
