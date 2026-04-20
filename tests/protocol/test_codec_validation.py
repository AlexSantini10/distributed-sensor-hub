"""Validate decode-time protocol payload validation."""

from __future__ import annotations

import json

import pytest

from protocol.codec import decode_message, message_from_dict
from protocol.messages import ProtocolValidationError


@pytest.mark.protocol
@pytest.mark.parametrize(
    "raw",
    [
        {
            "type": "JOIN_REQUEST",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"node_id": "", "host": "127.0.0.1", "port": 9000},
        },
        {
            "type": "PEER_LIST",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"peers": [{"node_id": "n2", "host": "127.0.0.1"}]},
        },
        {
            "type": "PING",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"timestamp": "bad"},
        },
        {
            "type": "SENSOR_UPDATE",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {
                "sensor_id": "sensor-a",
                "value": 10,
                "ts_ms": "bad",
                "origin": "node-1",
                "meta": {},
            },
        },
        {
            "type": "GET_STATE",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"unexpected": True},
        },
        {
            "type": "GET_DELTA",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"since_ts_ms": 10},
        },
        {
            "type": "FULL_SYNC_RESPONSE",
            "sender_id": "node-1",
            "timestamp": 1,
            "payload": {"state": {}},
        },
    ],
)
def test_message_from_dict_rejects_invalid_payloads(raw: dict[str, object]) -> None:
    """Assert malformed payloads fail clearly at decode time."""
    with pytest.raises(ProtocolValidationError):
        message_from_dict(raw)


@pytest.mark.protocol
def test_decode_message_rejects_incomplete_envelope() -> None:
    """Assert the transport decoder surfaces missing required fields."""
    raw = json.dumps({"type": "PING", "sender_id": "node-1", "payload": {}}).encode()
    with pytest.raises(ProtocolValidationError):
        decode_message(raw)
