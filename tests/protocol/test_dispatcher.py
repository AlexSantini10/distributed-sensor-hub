"""Validate protocol dispatcher registration and error behavior.

Responsibilities:
    - Assert that handlers are invoked for matching message types.
    - Confirm unknown message types are ignored safely.
    - Verify duplicate registration and handler failures surface correctly.
"""

import pytest

from protocol.dispatcher import MessageDispatcher, ProtocolError
from protocol.message import Message
from protocol.message_types import MessageType


def test_dispatch_calls_correct_handler() -> None:
    """Assert that dispatch routes a message to its registered handler.

    Returns:
        None: This test asserts successful handler lookup and invocation.
    """
    dispatcher = MessageDispatcher()
    called = {}

    def handler(msg: Message) -> None:
        """Record handler invocation for the dispatched message.

        Args:
            msg (Message): Protocol message passed by the dispatcher.

        Returns:
            None: This helper mutates the capture dictionary.
        """
        called["ok"] = True

    dispatcher.register(MessageType.PING, handler)

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={},
    )

    dispatcher.dispatch(msg)

    assert called.get("ok") is True


def test_dispatch_unknown_message_does_not_crash() -> None:
    """Assert that dispatch ignores unregistered message types.

    Returns:
        None: This test asserts safe no-op behavior for unknown handlers.
    """
    dispatcher = MessageDispatcher()

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={},
    )

    dispatcher.dispatch(msg)


def test_handler_exception_is_propagated() -> None:
    """Assert that dispatcher does not swallow handler exceptions.

    Returns:
        None: This test asserts failure propagation to the caller.
    """
    dispatcher = MessageDispatcher()

    def handler(msg: Message) -> None:
        """Raise a controlled exception for propagation testing.

        Args:
            msg (Message): Protocol message passed by the dispatcher.

        Returns:
            None: This helper always raises.

        Raises:
            RuntimeError: Always raised to test propagation.
        """
        raise RuntimeError("boom")

    dispatcher.register(MessageType.PING, handler)

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={},
    )

    with pytest.raises(RuntimeError):
        dispatcher.dispatch(msg)


def test_duplicate_handler_registration_fails() -> None:
    """Assert that one message type cannot be registered twice.

    Returns:
        None: This test asserts the dispatcher registration invariant.
    """
    dispatcher = MessageDispatcher()

    def handler(msg: Message) -> None:
        """Accept a dispatched message without side effects.

        Args:
            msg (Message): Protocol message passed by the dispatcher.

        Returns:
            None: This helper intentionally performs no action.
        """
        pass

    dispatcher.register(MessageType.PING, handler)

    with pytest.raises(ProtocolError):
        dispatcher.register(MessageType.PING, handler)
