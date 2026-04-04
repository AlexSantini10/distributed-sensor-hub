"""Serialize and deserialize typed protocol messages."""

from __future__ import annotations

import json
from typing import TypeVar

from protocol.contracts import MessageField, TextEncoding
from protocol.message_types import MessageType
from protocol.messages import (
    Message,
    PAYLOAD_TYPES,
    PayloadModel,
    ProtocolValidationError,
)
from utils.typing import JsonObject, JsonValue


PayloadT = TypeVar("PayloadT", bound=PayloadModel)


def message_to_dict(message: Message[PayloadT]) -> JsonObject:
    """Convert a typed message into the canonical wire dictionary."""
    return {
        MessageField.TYPE.value: message.msg_type.value,
        MessageField.SENDER_ID.value: message.sender_id,
        MessageField.TIMESTAMP.value: message.timestamp,
        MessageField.PAYLOAD.value: message.payload.to_mapping(),
    }


def encode_json(message: Message[PayloadT]) -> str:
    """Serialize a typed message into JSON text."""
    return json.dumps(message_to_dict(message))


def encode_message(message: Message[PayloadT]) -> bytes:
    """Serialize a typed message into UTF-8 JSON bytes."""
    return encode_json(message).encode(TextEncoding.UTF8.value)


def message_from_dict(raw: object) -> Message[PayloadModel]:
    """Build a typed message from a decoded JSON object."""
    if not isinstance(raw, dict):
        raise ProtocolValidationError("JSON object must be a dict")

    type_value = raw.get(MessageField.TYPE.value)
    if not isinstance(type_value, str):
        raise ProtocolValidationError(f"Missing field: {MessageField.TYPE.value}")

    try:
        msg_type = MessageType(type_value)
    except ValueError as exc:
        raise ProtocolValidationError(f"Invalid message type: {type_value}") from exc

    sender_id = raw.get(MessageField.SENDER_ID.value)
    if not isinstance(sender_id, str) or sender_id == "":
        raise ProtocolValidationError(
            f"Missing field: {MessageField.SENDER_ID.value}"
        )

    timestamp_value = raw.get(MessageField.TIMESTAMP.value)
    if timestamp_value is None:
        raise ProtocolValidationError(f"Missing field: {MessageField.TIMESTAMP.value}")
    if not isinstance(timestamp_value, int):
        raise ProtocolValidationError(
            f"{MessageField.TIMESTAMP.value} must be an int"
        )

    payload_cls = PAYLOAD_TYPES.get(msg_type)
    if payload_cls is None:
        raise ProtocolValidationError(f"No payload contract for {msg_type.value}")

    payload_raw: object = raw.get(MessageField.PAYLOAD.value, {})
    payload = payload_cls.from_mapping(payload_raw)
    return Message(
        msg_type=msg_type,
        sender_id=sender_id,
        payload=payload,
        timestamp=timestamp_value,
    )


def decode_message(json_bytes: bytes) -> Message[PayloadModel]:
    """Decode UTF-8 JSON bytes into a typed protocol message."""
    raw: JsonValue = json.loads(json_bytes.decode(TextEncoding.UTF8.value))
    return message_from_dict(raw)
