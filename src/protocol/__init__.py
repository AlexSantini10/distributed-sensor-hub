"""Expose the protocol types used to encode and route node messages.

Responsibilities:
    - Re-export the canonical message enum and message envelope container.
    - Re-export dispatcher types used by runtime networking assembly.
    - Provide a stable import surface for protocol-aware subsystems.
"""

from .message_types import MessageType
from .message import Message
from .factory import (
    build_ack,
    build_delta_unavailable,
    build_error,
    build_full_sync_request,
    build_full_sync_response,
    build_get_delta,
    build_get_state,
    build_gossip_state,
    build_join_request,
    build_peer_list,
    build_ping,
    build_pong,
    build_sensor_update,
)
from .dispatcher import MessageDispatcher, ProtocolError

__all__ = [
    "MessageType",
    "Message",
    "MessageDispatcher",
    "ProtocolError",
    "build_ack",
    "build_delta_unavailable",
    "build_error",
    "build_full_sync_request",
    "build_full_sync_response",
    "build_get_delta",
    "build_get_state",
    "build_gossip_state",
    "build_join_request",
    "build_peer_list",
    "build_ping",
    "build_pong",
    "build_sensor_update",
]
