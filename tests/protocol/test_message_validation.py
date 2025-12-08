from protocol.message import Message
from protocol.message_types import MessageType
import pytest

@pytest.mark.protocol
def test_valid_message_creation():
	msg = Message(
		msg_type=MessageType.PING,
		sender_id="node1",
		payload={"key": "value"}
	)

	assert msg.msg_type == MessageType.PING
	assert msg.sender_id == "node1"
	assert msg.payload == {"key": "value"}
	assert isinstance(msg.timestamp, int)

@pytest.mark.protocol
def test_invalid_msg_type():
	with pytest.raises(ValueError):
		Message(msg_type="PING", sender_id="n1", payload={})

@pytest.mark.protocol
def test_invalid_payload_type():
	with pytest.raises(ValueError):
		Message(MessageType.PING, "n1", payload="not a dict")

@pytest.mark.protocol
def test_invalid_timestamp():
	with pytest.raises(ValueError):
		Message(MessageType.PING, "n1", {}, timestamp="bad")
