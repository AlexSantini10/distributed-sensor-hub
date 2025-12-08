import time
import json
from protocol.message_types import MessageType


class Message:
	def __init__(self, msg_type: MessageType, sender_id: str, payload: dict, timestamp: int = None):
		self.msg_type = msg_type			# MessageType enum identifying message category
		self.sender_id = sender_id			# unique node identifier
		self.payload = payload or {}		# message-specific key-value data
		self.timestamp = timestamp if timestamp is not None else self._now_ms()  # logical time in ms

		self._validate()

	@staticmethod
	def _now_ms():
		# return current unix timestamp in milliseconds
		return int(time.time() * 1000)

	def _validate(self):
		# ensure msg_type is a valid MessageType enum
		if not isinstance(self.msg_type, MessageType):
			raise ValueError(f"msg_type must be MessageType, got {self.msg_type}")

		# sender_id must be a string identifier
		if not isinstance(self.sender_id, str):
			raise ValueError(f"sender_id must be str, got {type(self.sender_id)}")

		# payload must be a dictionary
		if not isinstance(self.payload, dict):
			raise ValueError(f"payload must be dict, got {type(self.payload)}")

		# timestamp must be an integer
		if not isinstance(self.timestamp, int):
			raise ValueError(f"timestamp must be int, got {type(self.timestamp)}")

	def to_dict(self) -> dict:
		# return python dict representation suitable for JSON serialization
		return {
			"type": self.msg_type.value,	# enum serialized as string
			"sender_id": self.sender_id,
			"timestamp": self.timestamp,
			"payload": self.payload
		}

	def to_json(self) -> str:
		# return message as JSON-formatted string
		return json.dumps(self.to_dict())

	def to_bytes(self) -> bytes:
		# return UTF-8 encoded JSON message bytes for TCP transmission
		return self.to_json().encode("utf-8")

	@classmethod
	def from_json(cls, raw: dict):
		# parse python dict into Message object with validation
		if not isinstance(raw, dict):
			raise ValueError("JSON object must be a dict")

		type_str = raw.get("type")		# expected message type string
		if type_str is None:
			raise ValueError("Missing field: type")

		try:
			msg_type = MessageType(type_str)
		except ValueError:
			raise ValueError(f"Invalid message type: {type_str}")

		sender_id = raw.get("sender_id")	# required field
		if sender_id is None:
			raise ValueError("Missing field: sender_id")

		return cls(
			msg_type=msg_type,
			sender_id=sender_id,
			payload=raw.get("payload", {}),	# optional payload
			timestamp=raw.get("timestamp")	# optional timestamp
		)

	@staticmethod
	def encode(msg) -> bytes:
		# wrapper for converting Message → bytes
		return msg.to_bytes()

	@staticmethod
	def decode(json_bytes: bytes):
		# decode UTF-8 bytes into Message instance
		raw = json.loads(json_bytes.decode("utf-8"))
		return Message.from_json(raw)
