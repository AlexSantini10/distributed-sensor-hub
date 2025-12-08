import pytest
from protocol.message import Message
from protocol.message_types import MessageType
import json

@pytest.mark.protocol
def test_to_dict_and_json():
	msg = Message(MessageType.PING, "nodeX", {"a": 1})

	d = msg.to_dict()
	assert d["type"] == "PING"
	assert d["sender_id"] == "nodeX"
	assert d["payload"] == {"a": 1}

	json_str = msg.to_json()
	assert isinstance(json_str, str)
	assert json.loads(json_str) == d
