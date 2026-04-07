"""Centralize shared protocol field names and wire-level constants.

Responsibilities:
    - Define stable JSON envelope keys used by protocol serialization.
    - Define stable payload keys reused across membership and replication messages.
    - Expose transport-adjacent constants used by protocol producers and consumers.
"""

from enum import StrEnum


class TextEncoding(StrEnum):
    """Enumerate text encodings used by protocol and HTTP serialization."""

    UTF8 = "utf-8"


class MessageField(StrEnum):
    """Enumerate top-level JSON envelope fields for protocol messages."""

    TYPE = "type"
    SENDER_ID = "sender_id"
    TIMESTAMP = "timestamp"
    PAYLOAD = "payload"


class MembershipField(StrEnum):
    """Enumerate membership payload keys exchanged between peers."""

    NODE_ID = "node_id"
    HOST = "host"
    PORT = "port"
    PEERS = "peers"


class SensorUpdateField(StrEnum):
    """Enumerate payload keys for replicated sensor updates."""

    SENSOR_ID = "sensor_id"
    VALUE = "value"
    TS_MS = "ts_ms"
    ORIGIN = "origin"
    META = "meta"


class FullSyncField(StrEnum):
    """Enumerate payload keys used by full-state synchronization messages."""

    STATE = "state"
    MEMBERSHIP = "membership"


class NetworkConstant(StrEnum):
    """Enumerate network-related string constants used by the runtime."""

    WILDCARD_HOST = "0.0.0.0"


class HttpContentType(StrEnum):
    """Enumerate HTTP content types emitted by the monitoring API."""

    JSON = "application/json"
