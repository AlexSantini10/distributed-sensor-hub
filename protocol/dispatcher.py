"""Route validated protocol messages to registered local handlers.

Responsibilities:
    - Maintain a single handler binding for each protocol message type.
    - Dispatch inbound messages according to their declared message type.
    - Enforce fail-fast behavior for handler registration and local handler errors.
"""

from typing import Callable, Dict

from protocol.message import Message
from protocol.message_types import MessageType


Handler = Callable[[Message], None]


class ProtocolError(Exception):
    """Signal protocol-level contract violations in local dispatcher setup."""


class MessageDispatcher:
    """Dispatch inbound messages to type-specific handlers.

    Attributes:
        _handlers: Mapping from message type to the handler responsible for that
            protocol message on the current node.
    """

    def __init__(self):
        """Initialize an empty dispatcher with no registered message handlers."""
        self._handlers: Dict[MessageType, Handler] = {}

    def register(self, msg_type: MessageType, handler: Handler) -> None:
        """Bind a handler to a message type.

        Args:
            msg_type: Protocol message type accepted by the handler.
            handler: Callable invoked for inbound messages of ``msg_type``.

        Returns:
            None.

        Raises:
            TypeError: If ``msg_type`` is not a ``MessageType`` or ``handler`` is
                not callable.
            ProtocolError: If a handler is already registered for ``msg_type``.
        """
        if not isinstance(msg_type, MessageType):
            raise TypeError("msg_type must be MessageType")

        if not callable(handler):
            raise TypeError("handler must be callable")

        if msg_type in self._handlers:
            raise ProtocolError(f"Handler already registered for {msg_type}")

        self._handlers[msg_type] = handler

    def dispatch(self, msg: Message) -> None:
        """Dispatch a message to the registered local handler.

        Unknown message types are ignored at the protocol boundary so that a
        node can tolerate peers that advertise newer capabilities. Handler
        exceptions are delegated to the local error policy.

        Args:
            msg: Validated protocol message to route.

        Returns:
            None.

        Raises:
            TypeError: If ``msg`` is not a ``Message`` instance.
            Exception: Re-raises any exception surfaced by the selected handler.
        """
        if not isinstance(msg, Message):
            raise TypeError("msg must be Message")

        handler = self._handlers.get(msg.msg_type)
        if handler is None:
            self._handle_unknown_message(msg)
            return

        try:
            handler(msg)
        except Exception as exc:
            self._handle_handler_error(msg, exc)

    def _handle_unknown_message(self, msg: Message) -> None:
        """Ignore an unsupported message type at the local protocol boundary.

        Args:
            msg: Message whose type has no registered handler on this node.

        Returns:
            None.
        """
        # protocol-level error: message type not supported by this node
        # decisione: loggare e ignorare
        # (nessun crash, nessun side effect)
        pass

    def _handle_handler_error(self, msg: Message, exc: Exception) -> None:
        """Propagate a handler failure according to the local fail-fast policy.

        Args:
            msg: Message being processed when the handler failed.
            exc: Exception raised by the handler.

        Returns:
            None.

        Raises:
            Exception: Always re-raises ``exc``.
        """
        # bug o errore di dominio nell'handler
        # decisione: propagare (fail-fast locale)
        raise exc
