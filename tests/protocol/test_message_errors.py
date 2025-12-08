import pytest
from protocol.message import Message

@pytest.mark.protocol
def test_from_json_missing_type():
	with pytest.raises(ValueError):
		Message.from_json({"sender_id": "n1"})

@pytest.mark.protocol
def test_from_json_invalid_type():
	with pytest.raises(ValueError):
		Message.from_json({"type": "NOPE", "sender_id": "n1"})

@pytest.mark.protocol
def test_from_json_missing_sender_id():
	with pytest.raises(ValueError):
		Message.from_json({"type": "PING"})
