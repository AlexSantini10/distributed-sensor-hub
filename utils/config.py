"""Load validated runtime configuration from environment variables.

Responsibilities:
    - Enforce required configuration keys for node startup.
    - Parse ports, bootstrap peers, and sensor definitions into typed values.
    - Reject invalid configuration before networking or state services start.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from dotenv import load_dotenv


class EnvKey(StrEnum):
    """Enumerate environment-variable keys used by the application."""

    NODE_ID = "NODE_ID"
    HOST = "HOST"
    PORT = "PORT"
    BOOTSTRAP_PEERS = "BOOTSTRAP_PEERS"
    LOG_LEVEL = "LOG_LEVEL"
    LOG_FILE = "LOG_FILE"
    CLEAR_LOG = "CLEAR_LOG"
    WEB_API_PORT = "WEB_API_PORT"
    HEARTBEAT_INTERVAL_MS = "HEARTBEAT_INTERVAL_MS"
    PHI_THRESHOLD_SUSPECT = "PHI_THRESHOLD_SUSPECT"
    PHI_THRESHOLD_DEAD = "PHI_THRESHOLD_DEAD"
    PHI_INITIAL_INTERVAL_S = "PHI_INITIAL_INTERVAL_S"
    REPLICATION_DELTA_MAXLEN = "REPLICATION_DELTA_MAXLEN"
    NETWORK_DELAY_MS = "NETWORK_DELAY_MS"
    NETWORK_DELAY_JITTER_MS = "NETWORK_DELAY_JITTER_MS"
    NETWORK_DELAY_SPIKE_PROB = "NETWORK_DELAY_SPIKE_PROB"
    NETWORK_DELAY_SPIKE_MS = "NETWORK_DELAY_SPIKE_MS"
    NETWORK_PACKET_LOSS_PROB = "NETWORK_PACKET_LOSS_PROB"
    SENSORS = "SENSORS"


class SensorEnvSuffix(StrEnum):
    """Enumerate per-sensor environment-variable suffixes."""

    TYPE = "TYPE"
    NAME = "NAME"
    PERIOD_MS = "PERIOD_MS"
    UNIT = "UNIT"
    MIN = "MIN"
    MAX = "MAX"
    P_TRUE = "P_TRUE"
    VALUES = "VALUES"
    START = "START"
    STEP_PCT = "STEP_PCT"
    SLOPE = "SLOPE"
    NOISE = "NOISE"
    BASELINE = "BASELINE"
    SPIKE_HEIGHT = "SPIKE_HEIGHT"
    P_SPIKE = "P_SPIKE"
    AMPLITUDE = "AMPLITUDE"
    FREQUENCY = "FREQUENCY"
    BASE = "BASE"
    LATENCY_MS = "LATENCY_MS"
    LATENCY_JITTER_MS = "LATENCY_JITTER_MS"


class LogLevel(StrEnum):
    """Enumerate allowed root logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SensorType(StrEnum):
    """Enumerate supported sensor kinds loaded from configuration."""

    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    INCREMENTAL = "incremental"
    TREND = "trend"
    SPIKE = "spike"
    WAVE = "wave"
    NOISE = "noise"


@dataclass(frozen=True)
class SensorConfig:
    """Represent one validated sensor configuration read from the environment.

    Attributes:
        index (int): Zero-based declaration order used to build a stable sensor ID.
        sensor_type (SensorType): Concrete sensor implementation to instantiate.
        name (str): Human-readable sensor name used in the generated sensor ID.
        period_ms (int): Publishing period in milliseconds.
        unit (str | None): Optional unit label emitted with sensor values.
        min_value (float | None): Numeric lower bound for ``NUMERIC`` sensors.
        max_value (float | None): Numeric upper bound for ``NUMERIC`` sensors.
        p_true (float | None): Probability of ``True`` for ``BOOLEAN`` sensors.
        values (tuple[str, ...]): Allowed categories for ``CATEGORICAL`` sensors.
        start (float | None): Starting value for ``INCREMENTAL`` and ``TREND`` sensors.
        step_pct (float | None): Percentage step for ``INCREMENTAL`` sensors.
        slope (float | None): Per-period slope for ``TREND`` sensors.
        noise (float | None): Noise factor for ``TREND`` and ``NOISE`` sensors.
        baseline (float | None): Baseline value for ``SPIKE`` sensors.
        spike_height (float | None): Spike height for ``SPIKE`` sensors.
        p_spike (float | None): Spike probability for ``SPIKE`` sensors.
        amplitude (float | None): Wave amplitude for ``WAVE`` sensors.
        frequency (float | None): Wave frequency for ``WAVE`` sensors.
        base (float | None): Baseline value for ``NOISE`` sensors.
        latency_ms (float): Optional base sensor-emission latency in milliseconds.
        latency_jitter_ms (float): Optional jitter radius applied to ``latency_ms``.
    """

    index: int
    sensor_type: SensorType
    name: str
    period_ms: int
    unit: str | None
    min_value: float | None = None
    max_value: float | None = None
    p_true: float | None = None
    values: tuple[str, ...] = ()
    start: float | None = None
    step_pct: float | None = None
    slope: float | None = None
    noise: float | None = None
    baseline: float | None = None
    spike_height: float | None = None
    p_spike: float | None = None
    amplitude: float | None = None
    frequency: float | None = None
    base: float | None = None
    latency_ms: float = 0.0
    latency_jitter_ms: float = 0.0

    @property
    def sensor_id(self) -> str:
        """Return the stable runtime sensor identifier for this config.

        Returns:
            str: Sensor identifier derived from name and declaration index.
        """
        return f"{self.name}@{self.index}"


@dataclass(frozen=True)
class Config:
    """Bundle validated node startup configuration.

    Attributes:
        node_id (str): Stable node identifier advertised to peers and used in LWW ties.
        host (str): Interface address used for the node's TCP server bind.
        port (int): TCP server port exposed by the node.
        bootstrap_peers (tuple[tuple[str, int], ...]): Initial peers contacted for cluster join.
        log_level (LogLevel): Root logging level applied during runtime startup.
        log_file (str): Path to the process log file.
        clear_log (bool): Whether startup should truncate the configured log file.
        web_api_port (int): TCP port exposed by the HTTP monitoring API.
        heartbeat_interval_ms (int): Heartbeat period used for periodic liveness probes.
        network_delay_ms (float): Artificial outbound network delay baseline in milliseconds.
        network_delay_jitter_ms (float): Delay jitter radius in milliseconds.
        network_delay_spike_prob (float): Probability of an additional delay spike per message.
        network_delay_spike_ms (float): Extra delay applied when a spike occurs.
        network_packet_loss_prob (float): Probability of dropping one outbound message.
        sensors (tuple[SensorConfig, ...]): Local sensors declared for this node.
    """

    node_id: str
    host: str
    port: int
    bootstrap_peers: tuple[tuple[str, int], ...]
    log_level: LogLevel
    log_file: str
    clear_log: bool
    web_api_port: int
    heartbeat_interval_ms: int
    phi_threshold_suspect: float
    phi_threshold_dead: float
    phi_initial_interval_s: float
    replication_delta_maxlen: int
    network_delay_ms: float
    network_delay_jitter_ms: float
    network_delay_spike_prob: float
    network_delay_spike_ms: float
    network_packet_loss_prob: float
    sensors: tuple[SensorConfig, ...]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Config":
        """Load and validate configuration from dotenv-backed environment state.

        Args:
            environ (Mapping[str, str] | None): Optional environment mapping used
                instead of ``os.environ``. When omitted, dotenv is loaded first.

        Returns:
            Config: Immutable runtime configuration for node bootstrap.

        Raises:
            RuntimeError: If any required variable is missing or invalid.
            ValueError: If a configured sensor definition is malformed.
            TypeError: If a required numeric sensor parameter is missing.
        """
        if environ is None:
            load_dotenv()
            env = dict(os.environ)
        else:
            env = dict(environ)

        node_id = _require_env(env, EnvKey.NODE_ID)
        host = _require_env(env, EnvKey.HOST)
        port = _parse_port(_require_env(env, EnvKey.PORT), EnvKey.PORT.value)

        log_level_raw = _require_env(env, EnvKey.LOG_LEVEL).upper()
        try:
            log_level = LogLevel(log_level_raw)
        except ValueError as exc:
            allowed = ", ".join(level.value for level in LogLevel)
            raise RuntimeError(
                f"Invalid LOG_LEVEL: {log_level_raw} (allowed: {allowed})"
            ) from exc

        log_file = _require_env(env, EnvKey.LOG_FILE)
        bootstrap_peers = tuple(
            _parse_peers(_get_optional_env(env, EnvKey.BOOTSTRAP_PEERS, default=""))
        )
        clear_log = _parse_bool(
            _get_optional_env(env, EnvKey.CLEAR_LOG, default="false")
        )
        web_api_port = _parse_port(
            _get_optional_env(env, EnvKey.WEB_API_PORT, default=str(port + 1000)),
            EnvKey.WEB_API_PORT.value,
        )
        heartbeat_interval_ms = _parse_positive_int(
            _get_optional_env(env, EnvKey.HEARTBEAT_INTERVAL_MS, default="1000"),
            EnvKey.HEARTBEAT_INTERVAL_MS.value,
        )
        phi_threshold_suspect = _parse_positive_float(
            _get_optional_env(env, EnvKey.PHI_THRESHOLD_SUSPECT, default="3.0"),
            EnvKey.PHI_THRESHOLD_SUSPECT.value,
        )
        phi_threshold_dead = _parse_positive_float(
            _get_optional_env(env, EnvKey.PHI_THRESHOLD_DEAD, default="8.0"),
            EnvKey.PHI_THRESHOLD_DEAD.value,
        )
        if phi_threshold_dead < phi_threshold_suspect:
            raise RuntimeError(
                "PHI_THRESHOLD_DEAD must be >= PHI_THRESHOLD_SUSPECT "
                f"(got dead={phi_threshold_dead}, suspect={phi_threshold_suspect})"
            )
        phi_initial_interval_s = _parse_positive_float(
            _get_optional_env(env, EnvKey.PHI_INITIAL_INTERVAL_S, default="1.0"),
            EnvKey.PHI_INITIAL_INTERVAL_S.value,
        )
        replication_delta_maxlen = _parse_positive_int(
            _get_optional_env(env, EnvKey.REPLICATION_DELTA_MAXLEN, default="512"),
            EnvKey.REPLICATION_DELTA_MAXLEN.value,
        )
        network_delay_ms = _parse_non_negative_float(
            _get_optional_env(env, EnvKey.NETWORK_DELAY_MS, default="0"),
            EnvKey.NETWORK_DELAY_MS.value,
        )
        network_delay_jitter_ms = _parse_non_negative_float(
            _get_optional_env(env, EnvKey.NETWORK_DELAY_JITTER_MS, default="0"),
            EnvKey.NETWORK_DELAY_JITTER_MS.value,
        )
        network_delay_spike_prob = _parse_probability(
            _get_optional_env(env, EnvKey.NETWORK_DELAY_SPIKE_PROB, default="0"),
            EnvKey.NETWORK_DELAY_SPIKE_PROB.value,
        )
        network_delay_spike_ms = _parse_non_negative_float(
            _get_optional_env(env, EnvKey.NETWORK_DELAY_SPIKE_MS, default="0"),
            EnvKey.NETWORK_DELAY_SPIKE_MS.value,
        )
        network_packet_loss_prob = _parse_probability(
            _get_optional_env(env, EnvKey.NETWORK_PACKET_LOSS_PROB, default="0"),
            EnvKey.NETWORK_PACKET_LOSS_PROB.value,
        )
        sensors = tuple(_parse_sensors(env))

        return cls(
            node_id=node_id,
            host=host,
            port=port,
            bootstrap_peers=bootstrap_peers,
            log_level=log_level,
            log_file=log_file,
            clear_log=clear_log,
            web_api_port=web_api_port,
            heartbeat_interval_ms=heartbeat_interval_ms,
            phi_threshold_suspect=phi_threshold_suspect,
            phi_threshold_dead=phi_threshold_dead,
            phi_initial_interval_s=phi_initial_interval_s,
            replication_delta_maxlen=replication_delta_maxlen,
            network_delay_ms=network_delay_ms,
            network_delay_jitter_ms=network_delay_jitter_ms,
            network_delay_spike_prob=network_delay_spike_prob,
            network_delay_spike_ms=network_delay_spike_ms,
            network_packet_loss_prob=network_packet_loss_prob,
            sensors=sensors,
        )

    @property
    def log_level_name(self) -> str:
        """Return the configured logging level as a string.

        Returns:
            str: Logging level name accepted by ``logging`` configuration APIs.
        """
        return self.log_level.value

    def should_clear_log(self) -> bool:
        """Report whether startup should truncate the configured log file.

        Returns:
            bool: ``True`` when log clearing is enabled and a log file is configured.
        """
        return self.clear_log and self.log_file != ""


def _require_env(env: Mapping[str, str], name: EnvKey | str) -> str:
    """Read one required environment variable.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        name (EnvKey | str): Environment-variable name that must be defined and non-empty.

    Returns:
        str: Stripped environment-variable value.

    Raises:
        RuntimeError: If the variable is missing or resolves to blank text.
    """
    key = _enum_value(name)
    value = env.get(key)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required env var: {key}")
    return value.strip()


def _get_optional_env(
    env: Mapping[str, str],
    name: EnvKey | str,
    *,
    default: str,
) -> str:
    """Read one optional environment variable with a string default.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        name (EnvKey | str): Environment-variable name to read.
        default (str): Fallback string used when the variable is absent.

    Returns:
        str: Environment value or ``default`` when absent.
    """
    key = _enum_value(name)
    value = env.get(key)
    return default if value is None else value.strip()


def _parse_port(raw: str, env_name: str = EnvKey.PORT.value) -> int:
    """Parse one TCP port value from text.

    Args:
        raw (str): Raw port string read from the environment.
        env_name (str): Environment-variable name used in validation errors.

    Returns:
        int: Valid TCP port number.

    Raises:
        RuntimeError: If the value is not an integer in the valid TCP port range.
    """
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be an integer, got: {raw}") from exc

    if not (0 < port < 65536):
        raise RuntimeError(f"Invalid {env_name} value: {port}")

    return port


def _parse_bool(raw: str) -> bool:
    """Parse a boolean flag using the project's existing env convention.

    Args:
        raw (str): Raw environment value.

    Returns:
        bool: ``True`` when the value is ``"true"`` case-insensitively.
    """
    return raw.lower() == "true"


def _parse_positive_int(raw: str, env_name: str) -> int:
    """Parse a strictly positive integer from configuration text."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be an integer, got: {raw}") from exc
    if value <= 0:
        raise RuntimeError(f"{env_name} must be > 0, got: {value}")
    return value


def _parse_positive_float(raw: str, env_name: str) -> float:
    """Parse a strictly positive float from configuration text."""
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be a float, got: {raw}") from exc
    if value <= 0:
        raise RuntimeError(f"{env_name} must be > 0, got: {value}")
    return value


def _parse_non_negative_float(raw: str, env_name: str) -> float:
    """Parse a non-negative float from configuration text."""
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{env_name} must be a float, got: {raw}") from exc
    if value < 0:
        raise RuntimeError(f"{env_name} must be >= 0, got: {value}")
    return value


def _parse_probability(raw: str, env_name: str) -> float:
    """Parse a probability value in the closed interval [0, 1]."""
    value = _parse_non_negative_float(raw, env_name)
    if value > 1:
        raise RuntimeError(f"{env_name} must be <= 1, got: {value}")
    return value


def _parse_peers(raw: str) -> list[tuple[str, int]]:
    """Parse bootstrap peers from a comma-separated ``host:port`` list.

    Args:
        raw (str): Raw peer list from the environment.

    Returns:
        list[tuple[str, int]]: Ordered bootstrap peers for initial membership joins.

    Raises:
        RuntimeError: If any peer entry does not follow the expected ``host:port`` format.
    """
    if raw.strip() == "":
        return []

    peers: list[tuple[str, int]] = []

    for item in raw.split(","):
        peer = item.strip()
        try:
            host, port = peer.split(":")
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid peer format: {peer} (expected host:port)"
            ) from exc
        peers.append((host.strip(), _parse_port(port, EnvKey.BOOTSTRAP_PEERS.value)))

    return peers


def _parse_sensors(env: Mapping[str, str]) -> list[SensorConfig]:
    """Parse all declared sensor definitions from the environment.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.

    Returns:
        list[SensorConfig]: Parsed sensors in declaration order.

    Raises:
        ValueError: If sensor declarations are malformed.
        TypeError: If required numeric sensor parameters are missing.
    """
    try:
        count = int(_get_optional_env(env, EnvKey.SENSORS, default="0"))
    except ValueError as exc:
        raise ValueError("SENSORS must be an integer") from exc

    sensors: list[SensorConfig] = []
    for index in range(count):
        sensors.append(_parse_sensor(env, index))
    return sensors


def _parse_sensor(env: Mapping[str, str], index: int) -> SensorConfig:
    """Parse one sensor definition by index.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        index (int): Zero-based sensor index.

    Returns:
        SensorConfig: Parsed sensor configuration.

    Raises:
        ValueError: If the sensor declaration is malformed.
        TypeError: If a required numeric field is missing.
    """
    sensor_type_raw = _get_sensor_value(env, index, SensorEnvSuffix.TYPE)
    if not sensor_type_raw:
        raise ValueError(f"Missing {_sensor_key(index, SensorEnvSuffix.TYPE)}")

    try:
        sensor_type = SensorType(sensor_type_raw)
    except ValueError as exc:
        raise ValueError(f"Unsupported sensor type: {sensor_type_raw}") from exc

    period_ms = int(
        _get_sensor_value_or_default(env, index, SensorEnvSuffix.PERIOD_MS, default="0")
    )
    if period_ms <= 0:
        raise ValueError(f"Invalid {_sensor_key(index, SensorEnvSuffix.PERIOD_MS)}")

    name = _get_sensor_value_or_default(
        env,
        index,
        SensorEnvSuffix.NAME,
        default=f"sensor_{index}",
    )
    unit = _get_sensor_value(env, index, SensorEnvSuffix.UNIT)
    latency_ms = _parse_non_negative_float(
        _get_sensor_value_or_default(
            env,
            index,
            SensorEnvSuffix.LATENCY_MS,
            default="0",
        ),
        _sensor_key(index, SensorEnvSuffix.LATENCY_MS),
    )
    latency_jitter_ms = _parse_non_negative_float(
        _get_sensor_value_or_default(
            env,
            index,
            SensorEnvSuffix.LATENCY_JITTER_MS,
            default="0",
        ),
        _sensor_key(index, SensorEnvSuffix.LATENCY_JITTER_MS),
    )

    if sensor_type == SensorType.NUMERIC:
        min_value = _require_sensor_float(env, index, SensorEnvSuffix.MIN)
        max_value = _require_sensor_float(env, index, SensorEnvSuffix.MAX)
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            min_value=min_value,
            max_value=max_value,
        )

    if sensor_type == SensorType.BOOLEAN:
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            p_true=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.P_TRUE,
                    default="0.5",
                )
            ),
        )

    if sensor_type == SensorType.CATEGORICAL:
        raw_values = _get_sensor_value_or_default(
            env,
            index,
            SensorEnvSuffix.VALUES,
            default="",
        )
        values = tuple(
            value.strip()
            for value in raw_values.split(",")
            if value.strip()
        )
        if not values:
            raise ValueError(
                f"{_sensor_key(index, SensorEnvSuffix.VALUES)} must not be empty"
            )
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            values=values,
        )

    if sensor_type == SensorType.INCREMENTAL:
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            start=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.START,
                    default="0",
                )
            ),
            step_pct=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.STEP_PCT,
                    default="1",
                )
            ),
        )

    if sensor_type == SensorType.TREND:
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            start=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.START,
                    default="0",
                )
            ),
            slope=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.SLOPE,
                    default="0.1",
                )
            ),
            noise=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.NOISE,
                    default="0.0",
                )
            ),
        )

    if sensor_type == SensorType.SPIKE:
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            baseline=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.BASELINE,
                    default="0",
                )
            ),
            spike_height=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.SPIKE_HEIGHT,
                    default="10",
                )
            ),
            p_spike=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.P_SPIKE,
                    default="0.2",
                )
            ),
        )

    if sensor_type == SensorType.WAVE:
        return SensorConfig(
            index=index,
            sensor_type=sensor_type,
            name=name,
            period_ms=period_ms,
            unit=unit,
            latency_ms=latency_ms,
            latency_jitter_ms=latency_jitter_ms,
            amplitude=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.AMPLITUDE,
                    default="1",
                )
            ),
            frequency=float(
                _get_sensor_value_or_default(
                    env,
                    index,
                    SensorEnvSuffix.FREQUENCY,
                    default="1",
                )
            ),
        )

    return SensorConfig(
        index=index,
        sensor_type=sensor_type,
        name=name,
        period_ms=period_ms,
        unit=unit,
        latency_ms=latency_ms,
        latency_jitter_ms=latency_jitter_ms,
        base=float(
            _get_sensor_value_or_default(
                env,
                index,
                SensorEnvSuffix.BASE,
                default="0",
            )
        ),
        noise=float(
            _get_sensor_value_or_default(
                env,
                index,
                SensorEnvSuffix.NOISE,
                default="1",
            )
        ),
    )


def _sensor_key(index: int, suffix: SensorEnvSuffix) -> str:
    """Build one fully qualified environment-variable key for a sensor.

    Args:
        index (int): Zero-based sensor index.
        suffix (SensorEnvSuffix): Sensor-variable suffix.

    Returns:
        str: Fully qualified sensor environment-variable key.
    """
    return f"SENSOR_{index}_{suffix.value}"


def _get_sensor_value(
    env: Mapping[str, str],
    index: int,
    suffix: SensorEnvSuffix,
    *,
    default: str | None = None,
) -> str | None:
    """Read one indexed sensor environment-variable value.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        index (int): Zero-based sensor index.
        suffix (SensorEnvSuffix): Sensor-variable suffix.
        default (str | None): Optional default used when the variable is absent.

    Returns:
        str | None: Trimmed environment value or ``default`` when absent.
    """
    key = _sensor_key(index, suffix)
    value = env.get(key)
    if value is None:
        return default
    return value.strip()


def _get_sensor_value_or_default(
    env: Mapping[str, str],
    index: int,
    suffix: SensorEnvSuffix,
    *,
    default: str,
) -> str:
    """Read one indexed sensor environment-variable value with a required fallback.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        index (int): Zero-based sensor index.
        suffix (SensorEnvSuffix): Sensor-variable suffix.
        default (str): Fallback used when the variable is absent.

    Returns:
        str: Trimmed environment value or ``default`` when absent.
    """
    value = _get_sensor_value(env, index, suffix, default=default)
    if value is None:
        return default
    return value


def _require_sensor_float(
    env: Mapping[str, str],
    index: int,
    suffix: SensorEnvSuffix,
) -> float:
    """Read one required numeric sensor value.

    Args:
        env (Mapping[str, str]): Environment mapping to read from.
        index (int): Zero-based sensor index.
        suffix (SensorEnvSuffix): Sensor-variable suffix.

    Returns:
        float: Parsed floating-point value.

    Raises:
        TypeError: If the underlying environment variable is missing.
        ValueError: If the value cannot be parsed as ``float``.
    """
    value = _get_sensor_value(env, index, suffix)
    if value is None:
        raise TypeError(f"float() argument must be a string or a real number, not 'NoneType'")
    return float(value)


def _enum_value(name: EnvKey | SensorEnvSuffix | str) -> str:
    """Normalize enum-backed configuration keys to their string value.

    Args:
        name (EnvKey | SensorEnvSuffix | str): Enum-backed or literal key name.

    Returns:
        str: String key name suitable for environment lookups.
    """
    if isinstance(name, StrEnum):
        return name.value
    return name


def load_config() -> Config:
    """Load and validate the process configuration from environment variables.

    Returns:
        Config: Immutable runtime configuration for node bootstrap.
    """
    return Config.from_env()
