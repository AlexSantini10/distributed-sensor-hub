"""Validate binary message encode and decode round-trips.

Responsibilities:
    - Assert that serialized protocol messages decode back to identical fields.
"""

import pytest

from protocol.message import Message
from protocol.message_types import MessageType


@pytest.mark.protocol
def test_encode_decode_roundtrip() -> None:
    """Assert that encoded messages decode without field loss.

    Returns:
        None: This test asserts message round-trip fidelity.
    """
    original = Message(MessageType.SENSOR_UPDATE, "node2", {"v": 10})

    data = Message.encode(original)
    assert isinstance(data, bytes)

    decoded = Message.decode(data)

    assert decoded.msg_type == original.msg_type
    assert decoded.sender_id == original.sender_id
    assert decoded.payload == original.payload
    assert decoded.timestamp == original.timestamp
