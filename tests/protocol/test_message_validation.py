"""Validate protocol-message construction invariants.

Responsibilities:
    - Assert that valid messages are accepted and invalid fields are rejected.
"""

import pytest

from protocol.messages import Message, PingPayload, ProtocolValidationError
from protocol.message_types import MessageType


@pytest.mark.protocol
def test_valid_message_creation() -> None:
    """Assert that a valid message populates all protocol fields.

    Returns:
        None: This test asserts successful message construction.
    """
    msg = Message(
        msg_type=MessageType.PING,
        sender_id="node1",
        payload=PingPayload(timestamp_ms=123),
    )

    assert msg.msg_type == MessageType.PING
    assert msg.sender_id == "node1"
    assert msg.payload == PingPayload(timestamp_ms=123)
    assert isinstance(msg.timestamp, int)


@pytest.mark.protocol
def test_invalid_msg_type() -> None:
    """Assert that non-enum message types are rejected.

    Returns:
        None: This test asserts message-type validation.
    """
    with pytest.raises(ProtocolValidationError):
        Message(msg_type="PING", sender_id="n1", payload=PingPayload())  # type: ignore[arg-type]


@pytest.mark.protocol
def test_invalid_payload_type() -> None:
    """Assert that payloads must be mapping objects.

    Returns:
        None: This test asserts payload-type validation.
    """
    with pytest.raises(ProtocolValidationError):
        Message(MessageType.PING, "n1", payload="not a payload")  # type: ignore[arg-type]


@pytest.mark.protocol
def test_invalid_timestamp() -> None:
    """Assert that timestamps must be integers.

    Returns:
        None: This test asserts timestamp-type validation.
    """
    with pytest.raises(ProtocolValidationError):
        Message(MessageType.PING, "n1", PingPayload(), timestamp="bad")  # type: ignore[arg-type]
