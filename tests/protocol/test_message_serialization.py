"""Validate protocol-message dict and JSON serialization.

Responsibilities:
    - Assert that message serialization preserves protocol fields exactly.
"""

import json

import pytest

from protocol.contracts import MessageField
from protocol.factory import build_ping


@pytest.mark.protocol
def test_to_dict_and_json() -> None:
    """Assert that dict and JSON serializers expose the same message payload.

    Returns:
        None: This test asserts serialization consistency.
    """
    msg = build_ping("nodeX", ping_timestamp_ms=123, timestamp=999)

    d = msg.to_dict()
    assert d[MessageField.TYPE.value] == "PING"
    assert d[MessageField.SENDER_ID.value] == "nodeX"
    assert d[MessageField.TIMESTAMP.value] == 999
    assert d[MessageField.PAYLOAD.value] == {"timestamp": 123}

    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert json.loads(json_str) == d
