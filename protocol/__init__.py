"""Expose protocol primitives used to encode, route, and initialize messages.

Responsibilities:
    - Re-export the canonical message enum and message container.
    - Re-export dispatcher types used by the node runtime.
    - Provide a stable import surface for protocol setup code.
"""

from .message_types import MessageType
from .message import Message
from .dispatcher import MessageDispatcher, ProtocolError

__all__ = ["MessageType", "Message", "MessageDispatcher", "ProtocolError"]
