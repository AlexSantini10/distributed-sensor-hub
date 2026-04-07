"""Validate centralized protocol message builders."""

from __future__ import annotations

import pytest

from protocol.factory import (
    build_ack,
    build_delta_unavailable,
    build_error,
    build_full_sync_request,
    build_full_sync_response,
    build_get_delta,
    build_get_state,
    build_gossip_state,
    build_join_request,
    build_peer_list,
    build_ping,
    build_pong,
    build_sensor_update,
)
from protocol.messages import PeerDescriptor, SensorMeta


@pytest.mark.protocol
@pytest.mark.parametrize(
    ("message", "expected_type", "expected_payload"),
    [
        (
            build_join_request("sender", "node-1", "127.0.0.1", 9000, timestamp=1),
            "JOIN_REQUEST",
            {"node_id": "node-1", "host": "127.0.0.1", "port": 9000},
        ),
        (
            build_peer_list(
                "sender",
                [PeerDescriptor(node_id="node-2", host="127.0.0.1", port=9001)],
                timestamp=2,
            ),
            "PEER_LIST",
            {
                "peers": [
                    {"node_id": "node-2", "host": "127.0.0.1", "port": 9001},
                ]
            },
        ),
        (
            build_ping("sender", ping_timestamp_ms=3, timestamp=4),
            "PING",
            {"timestamp": 3},
        ),
        (
            build_pong("sender", pong_timestamp_ms=5, timestamp=6),
            "PONG",
            {"timestamp": 5},
        ),
        (
            build_sensor_update(
                "sender",
                "sensor-a",
                42,
                7,
                "sender",
                meta=SensorMeta(unit="C", period_ms=1000),
                timestamp=8,
            ),
            "SENSOR_UPDATE",
            {
                "sensor_id": "sensor-a",
                "value": 42,
                "ts_ms": 7,
                "origin": "sender",
                "meta": {"unit": "C", "period_ms": 1000},
            },
        ),
        (
            build_gossip_state("sender", {"a": 1}, timestamp=9),
            "GOSSIP_STATE",
            {"state": {"a": 1}},
        ),
        (
            build_full_sync_request("sender", requester_id="sender", timestamp=10),
            "FULL_SYNC_REQUEST",
            {"requester_id": "sender"},
        ),
        (
            build_full_sync_response(
                "sender",
                {
                    "node-1": {
                        "node-1:s1": {
                            "value": 1,
                            "ts_ms": 1000,
                            "origin": "node-1",
                            "meta": {"unit": "C", "period_ms": 1000},
                        }
                    }
                },
                [PeerDescriptor(node_id="node-2", host="127.0.0.1", port=9001)],
                timestamp=11,
            ),
            "FULL_SYNC_RESPONSE",
            {
                "state": {
                    "node-1": {
                        "node-1:s1": {
                            "value": 1,
                            "ts_ms": 1000,
                            "origin": "node-1",
                            "meta": {"unit": "C", "period_ms": 1000},
                        }
                    }
                },
                "membership": {
                    "peers": [
                        {"node_id": "node-2", "host": "127.0.0.1", "port": 9001},
                    ]
                },
            },
        ),
        (
            build_get_state("sender", timestamp=12),
            "GET_STATE",
            {},
        ),
        (
            build_get_delta("sender", since_ts_ms=13, timestamp=14),
            "GET_DELTA",
            {"since_ts_ms": 13},
        ),
        (
            build_delta_unavailable("sender", "stale", timestamp=15),
            "DELTA_UNAVAILABLE",
            {"reason": "stale"},
        ),
        (
            build_error("sender", "bad request", timestamp=16),
            "ERROR",
            {"reason": "bad request"},
        ),
        (
            build_ack("sender", acked_type="PING", timestamp=17),
            "ACK",
            {"acked_type": "PING"},
        ),
    ],
)
def test_builder_creates_expected_message_shape(message, expected_type, expected_payload) -> None:
    """Assert every protocol builder uses the centralized typed schema."""
    assert message.msg_type.value == expected_type
    assert message.to_dict()["payload"] == expected_payload
