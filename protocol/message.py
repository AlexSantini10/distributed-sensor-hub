"""Define the canonical wire-format container for protocol messages.

Responsibilities:
    - Validate message fields before they enter the transport or dispatcher.
    - Serialize and deserialize the JSON message envelope used over TCP.
    - Preserve protocol metadata such as sender identity and logical timestamp.
"""

import json
import time

from protocol.message_types import MessageType


class Message:
	"""Represent a validated protocol message exchanged between nodes.

	Messages use a JSON object envelope with ``type``, ``sender_id``,
	``timestamp``, and ``payload`` fields. ``timestamp`` is a millisecond value
	carried with the message so downstream components can apply ordering or merge
	policies such as last-writer-wins without relying on transport order.

	Attributes:
		msg_type: Enumerated protocol message category.
		sender_id: Stable identifier of the node that emitted the message.
		payload: Message-specific JSON object carried as the protocol body.
		timestamp: Millisecond timestamp associated with the message envelope.
	"""

	def __init__(self, msg_type: MessageType, sender_id: str, payload: dict, timestamp: int = None):
		"""Initialize and validate a protocol message.

		Args:
			msg_type: Enumerated protocol message category.
			sender_id: Identifier of the node creating the message.
			payload: JSON-serializable mapping containing message-specific data.
			timestamp: Optional millisecond timestamp. When omitted, the current
				Unix time in milliseconds is used.

		Returns:
			None.

		Raises:
			ValueError: If any field violates the message contract.
		"""
		self.msg_type = msg_type
		self.sender_id = sender_id
		self.payload = payload or {}
		self.timestamp = timestamp if timestamp is not None else self._now_ms()

		self._validate()

	@staticmethod
	def _now_ms() -> int:
		"""Return the current Unix time in milliseconds.

		Returns:
			int: Current wall-clock time in milliseconds.
		"""
		return int(time.time() * 1000)

	def _validate(self) -> None:
		"""Validate the in-memory message fields against the wire contract.

		Returns:
			None.

		Raises:
			ValueError: If a field has the wrong type or a required field is invalid.
		"""
		if not isinstance(self.msg_type, MessageType):
			raise ValueError(f"msg_type must be MessageType, got {self.msg_type}")

		if not isinstance(self.sender_id, str):
			raise ValueError(f"sender_id must be str, got {type(self.sender_id)}")

		if not isinstance(self.payload, dict):
			raise ValueError(f"payload must be dict, got {type(self.payload)}")

		if not isinstance(self.timestamp, int):
			raise ValueError(f"timestamp must be int, got {type(self.timestamp)}")

	def to_dict(self) -> dict:
		"""Convert the message to the canonical JSON-object representation.

		Returns:
			dict: Message envelope with ``type``, ``sender_id``, ``timestamp``, and
				``payload`` fields.
		"""
		return {
			"type": self.msg_type.value,
			"sender_id": self.sender_id,
			"timestamp": self.timestamp,
			"payload": self.payload,
		}

	def to_json(self) -> str:
		"""Serialize the message envelope to a JSON string.

		Returns:
			str: JSON representation of the message.
		"""
		return json.dumps(self.to_dict())

	def to_bytes(self) -> bytes:
		"""Encode the message as UTF-8 JSON bytes for transport.

		Returns:
			bytes: UTF-8 encoded message envelope.
		"""
		return self.to_json().encode("utf-8")

	@classmethod
	def from_json(cls, raw: dict) -> "Message":
		"""Build a message from a decoded JSON object.

		Args:
			raw: Decoded JSON object representing a protocol message.

		Returns:
			Message: Validated protocol message instance.

		Raises:
			ValueError: If required fields are missing or invalid.
		"""
		if not isinstance(raw, dict):
			raise ValueError("JSON object must be a dict")

		type_str = raw.get("type")
		if type_str is None:
			raise ValueError("Missing field: type")

		try:
			msg_type = MessageType(type_str)
		except ValueError as exc:
			raise ValueError(f"Invalid message type: {type_str}") from exc

		sender_id = raw.get("sender_id")
		if sender_id is None:
			raise ValueError("Missing field: sender_id")

		return cls(
			msg_type=msg_type,
			sender_id=sender_id,
			payload=raw.get("payload", {}),
			timestamp=raw.get("timestamp"),
		)

	@staticmethod
	def encode(msg: "Message") -> bytes:
		"""Encode a message instance for transport.

		Args:
			msg: Message to encode.

		Returns:
			bytes: UTF-8 encoded message envelope.
		"""
		return msg.to_bytes()

	@staticmethod
	def decode(json_bytes: bytes) -> "Message":
		"""Decode UTF-8 JSON bytes into a validated message.

		Args:
			json_bytes: UTF-8 encoded JSON message envelope.

		Returns:
			Message: Decoded protocol message.

		Raises:
			UnicodeDecodeError: If ``json_bytes`` is not valid UTF-8.
			json.JSONDecodeError: If the byte sequence is not valid JSON.
			ValueError: If the decoded object does not satisfy the message contract.
		"""
		raw = json.loads(json_bytes.decode("utf-8"))
		return Message.from_json(raw)
