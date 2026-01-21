from typing import Callable, Dict
from protocol.message import Message
from protocol.message_types import MessageType


Handler = Callable[[Message], None]


class ProtocolError(Exception):
    pass


class MessageDispatcher:
    def __init__(self):
        self._handlers: Dict[MessageType, Handler] = {}

    def register(self, msg_type: MessageType, handler: Handler) -> None:
        if not isinstance(msg_type, MessageType):
            raise TypeError("msg_type must be MessageType")

        if not callable(handler):
            raise TypeError("handler must be callable")

        if msg_type in self._handlers:
            raise ProtocolError(f"Handler already registered for {msg_type}")

        self._handlers[msg_type] = handler

    def dispatch(self, msg: Message) -> None:
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
        # protocol-level error: message type not supported by this node
        # decisione: loggare e ignorare
        # (nessun crash, nessun side effect)
        pass

    def _handle_handler_error(self, msg: Message, exc: Exception) -> None:
        # bug o errore di dominio nell'handler
        # decisione: propagare (fail-fast locale)
        raise exc
