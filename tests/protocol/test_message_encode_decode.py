"""Validate binary message encode and decode round-trips.

Responsibilities:
    - Assert that serialized protocol messages decode back to identical fields.
"""

import pytest

from protocol.factory import build_sensor_update
from protocol.message import Message
from protocol.messages import SensorMeta, SensorUpdatePayload


@pytest.mark.protocol
def test_encode_decode_roundtrip() -> None:
    """Assert that encoded messages decode without field loss.

    Returns:
        None: This test asserts message round-trip fidelity.
    """
    original = build_sensor_update(
        sender_id="node2",
        sensor_id="sensor-a",
        value=10,
        ts_ms=500,
        origin="node2",
        meta=SensorMeta(unit="C", period_ms=1000),
        timestamp=900,
    )

    data = Message.encode(original)
    assert isinstance(data, bytes)

    decoded = Message.decode(data)

    assert decoded.msg_type == original.msg_type
    assert decoded.sender_id == original.sender_id
    assert isinstance(decoded.payload, SensorUpdatePayload)
    assert decoded.payload == original.payload
    assert decoded.timestamp == original.timestamp
