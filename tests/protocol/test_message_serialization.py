"""Validate protocol-message dict and JSON serialization.

Responsibilities:
    - Assert that message serialization preserves protocol fields exactly.
"""

import json

import pytest

from protocol.contracts import MessageField
from protocol.message import Message
from protocol.message_types import MessageType


@pytest.mark.protocol
def test_to_dict_and_json() -> None:
    """Assert that dict and JSON serializers expose the same message payload.

    Returns:
        None: This test asserts serialization consistency.
    """
    msg = Message(MessageType.PING, "nodeX", {"a": 1})

    d = msg.to_dict()
    assert d[MessageField.TYPE.value] == "PING"
    assert d[MessageField.SENDER_ID.value] == "nodeX"
    assert d[MessageField.PAYLOAD.value] == {"a": 1}

    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert json.loads(json_str) == d
