import pytest
from protocol.message import Message
from protocol.message_types import MessageType

@pytest.mark.protocol
def test_encode_decode_roundtrip():
	original = Message(MessageType.SENSOR_UPDATE, "node2", {"v": 10})

	data = Message.encode(original)
	assert isinstance(data, bytes)

	decoded = Message.decode(data)

	assert decoded.msg_type == original.msg_type
	assert decoded.sender_id == original.sender_id
	assert decoded.payload == original.payload
	assert decoded.timestamp == original.timestamp
