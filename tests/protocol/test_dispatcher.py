import pytest
from protocol.dispatcher import MessageDispatcher, ProtocolError
from protocol.message import Message
from protocol.message_types import MessageType


def test_dispatch_calls_correct_handler():
    dispatcher = MessageDispatcher()
    called = {}

    def handler(msg):
        called["ok"] = True

    dispatcher.register(MessageType.PING, handler)

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={}
    )

    dispatcher.dispatch(msg)

    assert called.get("ok") is True


def test_dispatch_unknown_message_does_not_crash():
    dispatcher = MessageDispatcher()

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={}
    )

    dispatcher.dispatch(msg)  # must not raise


def test_handler_exception_is_propagated():
    dispatcher = MessageDispatcher()

    def handler(msg):
        raise RuntimeError("boom")

    dispatcher.register(MessageType.PING, handler)

    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node-1",
        payload={}
    )

    with pytest.raises(RuntimeError):
        dispatcher.dispatch(msg)


def test_duplicate_handler_registration_fails():
    dispatcher = MessageDispatcher()

    def handler(msg):
        pass

    dispatcher.register(MessageType.PING, handler)

    with pytest.raises(ProtocolError):
        dispatcher.register(MessageType.PING, handler)
