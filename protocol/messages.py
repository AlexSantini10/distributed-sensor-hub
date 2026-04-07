"""Define typed protocol envelopes and payload contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import ClassVar, Generic, TypeVar

from protocol.contracts import MembershipField, MessageField, SensorUpdateField
from protocol.message_types import MessageType
from utils.typing import JsonObject, JsonValue


class ProtocolValidationError(ValueError):
    """Signal a protocol validation failure at the message boundary."""


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ProtocolValidationError(f"{field_name} must be a non-empty string")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise ProtocolValidationError(f"{field_name} must be an int")
    return value


def _require_mapping(value: object, field_name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ProtocolValidationError(f"{field_name} must be a JSON object")
    return dict(value)


@dataclass(frozen=True)
class PayloadModel:
    """Base class for typed payload contracts."""

    message_type: ClassVar[MessageType]

    def to_mapping(self) -> JsonObject:
        """Serialize the payload into the canonical JSON mapping."""
        raise NotImplementedError

    @classmethod
    def from_mapping(cls, raw: object) -> "PayloadModel":
        """Build a validated payload instance from a raw mapping."""
        raise NotImplementedError


@dataclass(frozen=True)
class EmptyPayload(PayloadModel):
    """Represent a message payload with no required fields."""

    message_type: ClassVar[MessageType]

    def to_mapping(self) -> JsonObject:
        """Return the canonical empty payload mapping."""
        return {}

    @classmethod
    def from_mapping(cls, raw: object) -> "EmptyPayload":
        """Validate that a payload mapping is empty."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        if data:
            raise ProtocolValidationError(
                f"{cls.message_type.value} payload must be empty"
            )
        return cls()


@dataclass(frozen=True)
class PeerDescriptor:
    """Represent one membership peer entry."""

    node_id: str
    host: str
    port: int

    def __post_init__(self) -> None:
        """Validate peer descriptor fields at construction time."""
        _require_non_empty_string(self.node_id, MembershipField.NODE_ID.value)
        _require_non_empty_string(self.host, MembershipField.HOST.value)
        _require_int(self.port, MembershipField.PORT.value)

    def to_mapping(self) -> JsonObject:
        """Serialize the peer descriptor into protocol payload shape."""
        return {
            MembershipField.NODE_ID.value: self.node_id,
            MembershipField.HOST.value: self.host,
            MembershipField.PORT.value: self.port,
        }

    @classmethod
    def from_mapping(cls, raw: object) -> "PeerDescriptor":
        """Build and validate one peer descriptor from a raw mapping."""
        data = _require_mapping(raw, "peer")
        return cls(
            node_id=_require_non_empty_string(
                data.get(MembershipField.NODE_ID.value),
                MembershipField.NODE_ID.value,
            ),
            host=_require_non_empty_string(
                data.get(MembershipField.HOST.value),
                MembershipField.HOST.value,
            ),
            port=_require_int(
                data.get(MembershipField.PORT.value),
                MembershipField.PORT.value,
            ),
        )


@dataclass(frozen=True)
class JoinRequestPayload(PayloadModel):
    """Represent a membership join announcement."""

    message_type: ClassVar[MessageType] = MessageType.JOIN_REQUEST

    node_id: str
    host: str
    port: int

    def __post_init__(self) -> None:
        """Validate join-request payload fields."""
        _require_non_empty_string(self.node_id, MembershipField.NODE_ID.value)
        _require_non_empty_string(self.host, MembershipField.HOST.value)
        _require_int(self.port, MembershipField.PORT.value)

    def to_mapping(self) -> JsonObject:
        """Serialize the payload into join-request mapping format."""
        return PeerDescriptor(
            node_id=self.node_id,
            host=self.host,
            port=self.port,
        ).to_mapping()

    @classmethod
    def from_mapping(cls, raw: object) -> "JoinRequestPayload":
        """Build a join-request payload from a peer descriptor mapping."""
        peer = PeerDescriptor.from_mapping(raw)
        return cls(node_id=peer.node_id, host=peer.host, port=peer.port)


@dataclass(frozen=True)
class PeerListPayload(PayloadModel):
    """Represent a membership peer-list response."""

    message_type: ClassVar[MessageType] = MessageType.PEER_LIST

    peers: tuple[PeerDescriptor, ...]

    def to_mapping(self) -> JsonObject:
        """Serialize the payload as a list of peer descriptor mappings."""
        return {
            MembershipField.PEERS.value: [peer.to_mapping() for peer in self.peers]
        }

    @classmethod
    def from_mapping(cls, raw: object) -> "PeerListPayload":
        """Build and validate a peer-list payload from a raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        peers_value = data.get(MembershipField.PEERS.value)
        if not isinstance(peers_value, list):
            raise ProtocolValidationError(
                f"{MembershipField.PEERS.value} must be a list"
            )
        return cls(peers=tuple(PeerDescriptor.from_mapping(peer) for peer in peers_value))


@dataclass(frozen=True)
class PingPayload(PayloadModel):
    """Represent a liveness ping."""

    message_type: ClassVar[MessageType] = MessageType.PING

    timestamp_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate optional ping timestamp when provided."""
        if self.timestamp_ms is not None:
            _require_int(self.timestamp_ms, "timestamp")

    def to_mapping(self) -> JsonObject:
        """Serialize the ping payload into its protocol mapping."""
        if self.timestamp_ms is None:
            return {}
        return {"timestamp": self.timestamp_ms}

    @classmethod
    def from_mapping(cls, raw: object) -> "PingPayload":
        """Build and validate a ping payload from a raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        timestamp_value = data.get("timestamp")
        if timestamp_value is None:
            return cls()
        return cls(timestamp_ms=_require_int(timestamp_value, "timestamp"))


@dataclass(frozen=True)
class PongPayload(PayloadModel):
    """Represent a liveness pong."""

    message_type: ClassVar[MessageType] = MessageType.PONG

    timestamp_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate optional pong timestamp when provided."""
        if self.timestamp_ms is not None:
            _require_int(self.timestamp_ms, "timestamp")

    def to_mapping(self) -> JsonObject:
        """Serialize the pong payload into its protocol mapping."""
        if self.timestamp_ms is None:
            return {}
        return {"timestamp": self.timestamp_ms}

    @classmethod
    def from_mapping(cls, raw: object) -> "PongPayload":
        """Build and validate a pong payload from a raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        timestamp_value = data.get("timestamp")
        if timestamp_value is None:
            return cls()
        return cls(timestamp_ms=_require_int(timestamp_value, "timestamp"))


@dataclass(frozen=True)
class SensorMeta:
    """Represent normalized sensor metadata."""

    unit: JsonValue = None
    period_ms: JsonValue = None

    def to_mapping(self) -> JsonObject:
        """Serialize sensor metadata into protocol mapping format."""
        return {"unit": self.unit, "period_ms": self.period_ms}

    @classmethod
    def from_mapping(cls, raw: object) -> "SensorMeta":
        """Build and validate sensor metadata from a raw mapping."""
        data = _require_mapping(raw, SensorUpdateField.META.value)
        return cls(unit=data.get("unit"), period_ms=data.get("period_ms"))


@dataclass(frozen=True)
class SensorUpdatePayload(PayloadModel):
    """Represent a replicated sensor update."""

    message_type: ClassVar[MessageType] = MessageType.SENSOR_UPDATE

    sensor_id: str
    value: JsonValue
    ts_ms: int
    origin: str
    meta: SensorMeta = field(default_factory=SensorMeta)

    def __post_init__(self) -> None:
        """Validate required sensor-update fields."""
        _require_non_empty_string(self.sensor_id, SensorUpdateField.SENSOR_ID.value)
        _require_int(self.ts_ms, SensorUpdateField.TS_MS.value)
        _require_non_empty_string(self.origin, SensorUpdateField.ORIGIN.value)

    def to_mapping(self) -> JsonObject:
        """Serialize the sensor update into protocol payload mapping."""
        return {
            SensorUpdateField.SENSOR_ID.value: self.sensor_id,
            SensorUpdateField.VALUE.value: self.value,
            SensorUpdateField.TS_MS.value: self.ts_ms,
            SensorUpdateField.ORIGIN.value: self.origin,
            SensorUpdateField.META.value: self.meta.to_mapping(),
        }

    @classmethod
    def from_mapping(cls, raw: object) -> "SensorUpdatePayload":
        """Build and validate a sensor-update payload from raw input."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        meta_value = data.get(SensorUpdateField.META.value, {})
        return cls(
            sensor_id=_require_non_empty_string(
                data.get(SensorUpdateField.SENSOR_ID.value),
                SensorUpdateField.SENSOR_ID.value,
            ),
            value=data.get(SensorUpdateField.VALUE.value),
            ts_ms=_require_int(
                data.get(SensorUpdateField.TS_MS.value),
                SensorUpdateField.TS_MS.value,
            ),
            origin=_require_non_empty_string(
                data.get(SensorUpdateField.ORIGIN.value),
                SensorUpdateField.ORIGIN.value,
            ),
            meta=SensorMeta.from_mapping(meta_value),
        )


@dataclass(frozen=True)
class GossipStatePayload(PayloadModel):
    """Represent a gossip-state payload."""

    message_type: ClassVar[MessageType] = MessageType.GOSSIP_STATE

    state: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate that gossip state is a JSON mapping."""
        _require_mapping(self.state, "state")

    def to_mapping(self) -> JsonObject:
        """Serialize gossip state into protocol payload mapping."""
        return {"state": dict(self.state)}

    @classmethod
    def from_mapping(cls, raw: object) -> "GossipStatePayload":
        """Build and validate a gossip-state payload from a raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        return cls(state=_require_mapping(data.get("state", {}), "state"))


@dataclass(frozen=True)
class FullSyncRequestPayload(PayloadModel):
    """Represent a full-state sync request."""

    message_type: ClassVar[MessageType] = MessageType.FULL_SYNC_REQUEST

    requester_id: str | None = None

    def __post_init__(self) -> None:
        """Validate optional requester identifier when present."""
        if self.requester_id is not None:
            _require_non_empty_string(self.requester_id, "requester_id")

    def to_mapping(self) -> JsonObject:
        """Serialize the full-sync request payload."""
        if self.requester_id is None:
            return {}
        return {"requester_id": self.requester_id}

    @classmethod
    def from_mapping(cls, raw: object) -> "FullSyncRequestPayload":
        """Build and validate a full-sync request payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        requester_id = data.get("requester_id")
        if requester_id is None:
            return cls()
        return cls(
            requester_id=_require_non_empty_string(requester_id, "requester_id")
        )


@dataclass(frozen=True)
class FullSyncResponsePayload(PayloadModel):
    """Represent a full-state sync response."""

    message_type: ClassVar[MessageType] = MessageType.FULL_SYNC_RESPONSE

    state: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate that full-sync state is a JSON mapping."""
        _require_mapping(self.state, "state")

    def to_mapping(self) -> JsonObject:
        """Serialize full-sync response state mapping."""
        return {"state": dict(self.state)}

    @classmethod
    def from_mapping(cls, raw: object) -> "FullSyncResponsePayload":
        """Build and validate full-sync response payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        return cls(state=_require_mapping(data.get("state", {}), "state"))


@dataclass(frozen=True)
class GetStatePayload(EmptyPayload):
    """Represent a request for current state."""

    message_type: ClassVar[MessageType] = MessageType.GET_STATE


@dataclass(frozen=True)
class GetDeltaPayload(PayloadModel):
    """Represent a request for state delta since a timestamp."""

    message_type: ClassVar[MessageType] = MessageType.GET_DELTA

    since_ts_ms: int

    def __post_init__(self) -> None:
        """Validate required delta cursor timestamp."""
        _require_int(self.since_ts_ms, "since_ts_ms")

    def to_mapping(self) -> JsonObject:
        """Serialize delta request payload into protocol mapping."""
        return {"since_ts_ms": self.since_ts_ms}

    @classmethod
    def from_mapping(cls, raw: object) -> "GetDeltaPayload":
        """Build and validate delta request payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        return cls(since_ts_ms=_require_int(data.get("since_ts_ms"), "since_ts_ms"))


@dataclass(frozen=True)
class DeltaUnavailablePayload(PayloadModel):
    """Represent a failure to provide an incremental delta."""

    message_type: ClassVar[MessageType] = MessageType.DELTA_UNAVAILABLE

    reason: str

    def __post_init__(self) -> None:
        """Validate the delta-unavailable reason string."""
        _require_non_empty_string(self.reason, "reason")

    def to_mapping(self) -> JsonObject:
        """Serialize delta-unavailable payload into protocol mapping."""
        return {"reason": self.reason}

    @classmethod
    def from_mapping(cls, raw: object) -> "DeltaUnavailablePayload":
        """Build and validate delta-unavailable payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        return cls(reason=_require_non_empty_string(data.get("reason"), "reason"))


@dataclass(frozen=True)
class ErrorPayload(PayloadModel):
    """Represent a protocol-level error response."""

    message_type: ClassVar[MessageType] = MessageType.ERROR

    reason: str

    def __post_init__(self) -> None:
        """Validate the protocol error reason string."""
        _require_non_empty_string(self.reason, "reason")

    def to_mapping(self) -> JsonObject:
        """Serialize protocol error payload into mapping form."""
        return {"reason": self.reason}

    @classmethod
    def from_mapping(cls, raw: object) -> "ErrorPayload":
        """Build and validate protocol error payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        return cls(reason=_require_non_empty_string(data.get("reason"), "reason"))


@dataclass(frozen=True)
class AckPayload(PayloadModel):
    """Represent a generic acknowledgement."""

    message_type: ClassVar[MessageType] = MessageType.ACK

    acked_type: str | None = None

    def __post_init__(self) -> None:
        """Validate optional acknowledgement target type."""
        if self.acked_type is not None:
            _require_non_empty_string(self.acked_type, "acked_type")

    def to_mapping(self) -> JsonObject:
        """Serialize acknowledgement payload into protocol mapping."""
        if self.acked_type is None:
            return {}
        return {"acked_type": self.acked_type}

    @classmethod
    def from_mapping(cls, raw: object) -> "AckPayload":
        """Build and validate acknowledgement payload from raw mapping."""
        data = _require_mapping(raw, MessageField.PAYLOAD.value)
        acked_type = data.get("acked_type")
        if acked_type is None:
            return cls()
        return cls(acked_type=_require_non_empty_string(acked_type, "acked_type"))


PayloadT = TypeVar("PayloadT", bound=PayloadModel)


@dataclass(frozen=True)
class Message(Generic[PayloadT]):
    """Represent a validated protocol envelope with a typed payload."""

    msg_type: MessageType
    sender_id: str
    payload: PayloadT
    timestamp: int | None = field(default_factory=lambda: int(time.time() * 1000))

    def __post_init__(self) -> None:
        """Validate message envelope and payload consistency."""
        if not isinstance(self.msg_type, MessageType):
            raise ProtocolValidationError("msg_type must be MessageType")
        _require_non_empty_string(self.sender_id, MessageField.SENDER_ID.value)
        if not isinstance(self.payload, PayloadModel):
            raise ProtocolValidationError("payload must be a PayloadModel")
        if self.payload.message_type is not self.msg_type:
            raise ProtocolValidationError("payload type does not match message type")
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", int(time.time() * 1000))
        _require_int(self.timestamp, MessageField.TIMESTAMP.value)

    def to_dict(self) -> JsonObject:
        """Serialize the message into a validated dictionary envelope."""
        from protocol.codec import message_to_dict

        return message_to_dict(self)

    def to_json(self) -> str:
        """Serialize the message into JSON text."""
        from protocol.codec import encode_json

        return encode_json(self)

    def to_bytes(self) -> bytes:
        """Serialize the message into transport-ready bytes."""
        from protocol.codec import encode_message

        return encode_message(self)

    @classmethod
    def from_json(cls, raw: object) -> "Message[PayloadModel]":
        """Decode a message instance from a raw JSON-like object."""
        from protocol.codec import message_from_dict

        return message_from_dict(raw)

    @staticmethod
    def encode(msg: "Message[PayloadModel]") -> bytes:
        """Encode a message object to bytes via protocol codec."""
        from protocol.codec import encode_message

        return encode_message(msg)

    @staticmethod
    def decode(json_bytes: bytes) -> "Message[PayloadModel]":
        """Decode a message object from protocol-encoded bytes."""
        from protocol.codec import decode_message

        return decode_message(json_bytes)


PAYLOAD_TYPES: dict[MessageType, type[PayloadModel]] = {
    MessageType.JOIN_REQUEST: JoinRequestPayload,
    MessageType.PEER_LIST: PeerListPayload,
    MessageType.PING: PingPayload,
    MessageType.PONG: PongPayload,
    MessageType.SENSOR_UPDATE: SensorUpdatePayload,
    MessageType.GOSSIP_STATE: GossipStatePayload,
    MessageType.FULL_SYNC_REQUEST: FullSyncRequestPayload,
    MessageType.FULL_SYNC_RESPONSE: FullSyncResponsePayload,
    MessageType.GET_STATE: GetStatePayload,
    MessageType.GET_DELTA: GetDeltaPayload,
    MessageType.DELTA_UNAVAILABLE: DeltaUnavailablePayload,
    MessageType.ERROR: ErrorPayload,
    MessageType.ACK: AckPayload,
}
