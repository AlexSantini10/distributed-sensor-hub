"""Central builders for typed protocol messages."""

from __future__ import annotations

from protocol.message_types import MessageType
from protocol.messages import (
    AckPayload,
    DeltaUnavailablePayload,
    ErrorPayload,
    FullSyncRequestPayload,
    FullSyncResponsePayload,
    GetDeltaPayload,
    GetStatePayload,
    GossipStatePayload,
    JoinRequestPayload,
    Message,
    PeerDescriptor,
    PeerListPayload,
    PingPayload,
    PongPayload,
    SensorMeta,
    SensorUpdatePayload,
)
from utils.typing import JsonObject, JsonValue, NodeSnapshot


def build_join_request(
    sender_id: str,
    node_id: str,
    host: str,
    port: int,
    *,
    timestamp: int | None = None,
) -> Message[JoinRequestPayload]:
    """Build a ``JOIN_REQUEST`` message."""
    return Message(
        msg_type=MessageType.JOIN_REQUEST,
        sender_id=sender_id,
        payload=JoinRequestPayload(node_id=node_id, host=host, port=port),
        timestamp=timestamp,
    )


def build_peer_list(
    sender_id: str,
    peers: list[PeerDescriptor] | tuple[PeerDescriptor, ...],
    *,
    timestamp: int | None = None,
) -> Message[PeerListPayload]:
    """Build a ``PEER_LIST`` message."""
    return Message(
        msg_type=MessageType.PEER_LIST,
        sender_id=sender_id,
        payload=PeerListPayload(peers=tuple(peers)),
        timestamp=timestamp,
    )


def build_ping(
    sender_id: str,
    *,
    ping_timestamp_ms: int | None = None,
    timestamp: int | None = None,
) -> Message[PingPayload]:
    """Build a ``PING`` message."""
    return Message(
        msg_type=MessageType.PING,
        sender_id=sender_id,
        payload=PingPayload(timestamp_ms=ping_timestamp_ms),
        timestamp=timestamp,
    )


def build_pong(
    sender_id: str,
    *,
    pong_timestamp_ms: int | None = None,
    timestamp: int | None = None,
) -> Message[PongPayload]:
    """Build a ``PONG`` message."""
    return Message(
        msg_type=MessageType.PONG,
        sender_id=sender_id,
        payload=PongPayload(timestamp_ms=pong_timestamp_ms),
        timestamp=timestamp,
    )


def build_sensor_update(
    sender_id: str,
    sensor_id: str,
    value: JsonValue,
    ts_ms: int,
    origin: str,
    *,
    meta: SensorMeta | None = None,
    seq: int | None = None,
    timestamp: int | None = None,
) -> Message[SensorUpdatePayload]:
    """Build a ``SENSOR_UPDATE`` message."""
    return Message(
        msg_type=MessageType.SENSOR_UPDATE,
        sender_id=sender_id,
        payload=SensorUpdatePayload(
            sensor_id=sensor_id,
            value=value,
            ts_ms=ts_ms,
            origin=origin,
            meta=meta if meta is not None else SensorMeta(),
            seq=seq,
        ),
        timestamp=timestamp,
    )


def build_gossip_state(
    sender_id: str,
    state: JsonObject,
    *,
    timestamp: int | None = None,
) -> Message[GossipStatePayload]:
    """Build a ``GOSSIP_STATE`` message."""
    return Message(
        msg_type=MessageType.GOSSIP_STATE,
        sender_id=sender_id,
        payload=GossipStatePayload(state=state),
        timestamp=timestamp,
    )


def build_full_sync_request(
    sender_id: str,
    *,
    requester_id: str | None = None,
    timestamp: int | None = None,
) -> Message[FullSyncRequestPayload]:
    """Build a ``FULL_SYNC_REQUEST`` message."""
    return Message(
        msg_type=MessageType.FULL_SYNC_REQUEST,
        sender_id=sender_id,
        payload=FullSyncRequestPayload(requester_id=requester_id),
        timestamp=timestamp,
    )


def build_full_sync_response(
    sender_id: str,
    state: NodeSnapshot,
    membership: list[PeerDescriptor] | tuple[PeerDescriptor, ...],
    *,
    timestamp: int | None = None,
) -> Message[FullSyncResponsePayload]:
    """Build a ``FULL_SYNC_RESPONSE`` message."""
    return Message(
        msg_type=MessageType.FULL_SYNC_RESPONSE,
        sender_id=sender_id,
        payload=FullSyncResponsePayload(
            state=state,
            membership=tuple(membership),
        ),
        timestamp=timestamp,
    )


def build_get_state(
    sender_id: str,
    *,
    timestamp: int | None = None,
) -> Message[GetStatePayload]:
    """Build a ``GET_STATE`` message."""
    return Message(
        msg_type=MessageType.GET_STATE,
        sender_id=sender_id,
        payload=GetStatePayload(),
        timestamp=timestamp,
    )


def build_get_delta(
    sender_id: str,
    from_seq: int,
    *,
    timestamp: int | None = None,
) -> Message[GetDeltaPayload]:
    """Build a ``GET_DELTA`` message."""
    return Message(
        msg_type=MessageType.GET_DELTA,
        sender_id=sender_id,
        payload=GetDeltaPayload(from_seq=from_seq),
        timestamp=timestamp,
    )


def build_delta_unavailable(
    sender_id: str,
    reason: str,
    *,
    timestamp: int | None = None,
) -> Message[DeltaUnavailablePayload]:
    """Build a ``DELTA_UNAVAILABLE`` message."""
    return Message(
        msg_type=MessageType.DELTA_UNAVAILABLE,
        sender_id=sender_id,
        payload=DeltaUnavailablePayload(reason=reason),
        timestamp=timestamp,
    )


def build_error(
    sender_id: str,
    reason: str,
    *,
    timestamp: int | None = None,
) -> Message[ErrorPayload]:
    """Build an ``ERROR`` message."""
    return Message(
        msg_type=MessageType.ERROR,
        sender_id=sender_id,
        payload=ErrorPayload(reason=reason),
        timestamp=timestamp,
    )


def build_ack(
    sender_id: str,
    *,
    acked_type: str | None = None,
    timestamp: int | None = None,
) -> Message[AckPayload]:
    """Build an ``ACK`` message."""
    return Message(
        msg_type=MessageType.ACK,
        sender_id=sender_id,
        payload=AckPayload(acked_type=acked_type),
        timestamp=timestamp,
    )
