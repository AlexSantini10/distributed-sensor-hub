"""Handle protocol heartbeats for membership liveness updates."""

from collections.abc import Callable
import time

from membership.peer_table import PeerTable
from protocol.factory import build_pong
from protocol.message import Message
from protocol.messages import PingPayload, PongPayload
from utils.logging import get_logger
from utils.typing import LoggerLike, SenderLike


def make_heartbeat_handlers(
    *,
    peer_table: PeerTable,
    send: SenderLike,
    self_node_id: str,
    on_peer_alive: Callable[[str], None] | None = None,
) -> tuple[Callable[[Message], None], Callable[[Message], None]]:
    """Create handlers for ``PING`` and ``PONG`` liveness traffic."""
    log: LoggerLike = get_logger(__name__, self_node_id)

    def _mark_alive_and_record(
        *,
        peer_id: str,
        sender_timestamp_ms: int | None,
    ) -> None:
        update = peer_table.record_heartbeat(
            peer_id,
            heartbeat_at=time.time(),
            sender_timestamp_ms=sender_timestamp_ms,
            arrived_at_monotonic_s=time.monotonic(),
        )
        if update.reason == "peer_not_found":
            log.debug(f"Heartbeat received from unknown peer {peer_id}")
            return
        if update.status.changed and update.peer is not None:
            log.info(
                "Membership transition on heartbeat: "
                f"peer={peer_id} "
                f"from={update.status.previous_status} to={update.status.new_status} "
                f"phi={update.peer.phi:.3f} "
                f"event_ts_ms={update.peer.status_ts_ms}"
            )

    def handle_ping(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, PingPayload):
            log.warning("Invalid PING payload")
            return
        if msg.sender_id == self_node_id:
            log.debug("Ignored self PING")
            return

        _mark_alive_and_record(
            peer_id=msg.sender_id,
            sender_timestamp_ms=payload.timestamp_ms,
        )
        if on_peer_alive is not None:
            on_peer_alive(msg.sender_id)

        pong = build_pong(
            sender_id=self_node_id,
            pong_timestamp_ms=int(time.time() * 1000),
        )
        try:
            send(msg.sender_id, pong)
        except Exception:
            log.warning(f"Failed to send PONG to {msg.sender_id}", exc_info=True)

    def handle_pong(msg: Message) -> None:
        payload = msg.payload
        if not isinstance(payload, PongPayload):
            log.warning("Invalid PONG payload")
            return
        if msg.sender_id == self_node_id:
            log.debug("Ignored self PONG")
            return

        _mark_alive_and_record(
            peer_id=msg.sender_id,
            sender_timestamp_ms=payload.timestamp_ms,
        )
        if on_peer_alive is not None:
            on_peer_alive(msg.sender_id)

    return handle_ping, handle_pong
