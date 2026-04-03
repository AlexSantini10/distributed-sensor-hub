"""Expose the protocol types used to encode and route node messages.

Responsibilities:
    - Re-export the canonical message enum and message envelope container.
    - Re-export dispatcher types used by runtime networking assembly.
    - Provide a stable import surface for protocol-aware subsystems.
"""

from .message_types import MessageType
from .message import Message
from .dispatcher import MessageDispatcher, ProtocolError

__all__ = ["MessageType", "Message", "MessageDispatcher", "ProtocolError"]
