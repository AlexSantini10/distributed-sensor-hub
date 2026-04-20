"""Assemble protocol routing and handler bindings for a runtime node."""

from collections.abc import Callable
import time

from gossip.handlers import make_gossip_state_handler
from membership.peer import Peer as MembershipPeer
from membership.peer_table import PeerTable
from protocol.dispatcher import MessageDispatcher
from protocol.handlers.heartbeat import make_heartbeat_handlers
from protocol.handlers.membership import make_membership_handlers
from protocol.handlers.state_sync import (
    handle_full_sync_request,
    handle_full_sync_response,
    handle_get_delta,
    handle_sensor_update,
    make_delta_unavailable_handler,
    make_full_sync_request_handler,
    make_full_sync_response_handler,
    make_get_delta_handler,
    make_sensor_update_handler,
)
from protocol.message_types import MessageType
from protocol.message import Message
from protocol.messages import AckPayload, ErrorPayload
from utils.logging import get_logger
from utils.typing import SenderLike, StateWorkerLike


OnPeerDiscovered = Callable[[MembershipPeer], None]


def setup_protocol(
    self_node_id: str,
    send_function: SenderLike,
    state_worker: StateWorkerLike | None = None,
    on_peer_discovered: OnPeerDiscovered | None = None,
    sensor_update_source_classifier: Callable[[str], str] | None = None,
    sensor_update_seq_observer: Callable[[str, str, int], None] | None = None,
    phi_threshold_suspect: float = 3.0,
    phi_threshold_dead: float = 8.0,
    phi_initial_interval_s: float = 1.0,
) -> tuple[MessageDispatcher, PeerTable]:
    """Build the protocol dispatcher and register message handlers.

    Args:
        self_node_id (str): Local node identifier used by protocol handlers.
        send_function (SenderLike): Transport callback used by outbound handlers.
        state_worker (StateWorkerLike | None): Optional state worker for state-sync handlers.
        on_peer_discovered (OnPeerDiscovered | None): Optional callback notified for new peers.
        sensor_update_source_classifier (Callable[[str], str] | None): Optional
            sender classifier used to tag inbound ``SENSOR_UPDATE`` source.
        sensor_update_seq_observer (Callable[[str, str, int], None] | None): Optional
            observer notified with ``(sender_id, source, seq)`` for inbound updates.
        phi_threshold_suspect (float): Phi threshold for ``suspected`` transitions.
        phi_threshold_dead (float): Phi threshold for ``dead`` transitions.
        phi_initial_interval_s (float): Initial heartbeat interval estimate in seconds.

    Returns:
        tuple[MessageDispatcher, PeerTable]: Configured dispatcher and shared peer table.
    """
    dispatcher = MessageDispatcher()
    peer_table = PeerTable(
        self_node_id=self_node_id,
        phi_threshold_suspect=phi_threshold_suspect,
        phi_threshold_dead=phi_threshold_dead,
        phi_initial_interval_s=phi_initial_interval_s,
    )

    join_handler, peer_list_handler = make_membership_handlers(
        peer_table=peer_table,
        send=send_function,
        self_node_id=self_node_id,
        on_peer_discovered=on_peer_discovered,
    )

    ping_handler, pong_handler = make_heartbeat_handlers(
        peer_table=peer_table,
        send=send_function,
        self_node_id=self_node_id,
    )

    def _with_direct_observation(
        handler: Callable[[Message], None],
    ) -> Callable[[Message], None]:
        """Wrap a handler and record direct transport evidence after success."""

        def wrapped(msg: Message) -> None:
            handler(msg)
            if msg.sender_id == self_node_id:
                return
            if msg.msg_type in {MessageType.PING, MessageType.PONG}:
                return
            peer_table.record_direct_message(
                msg.sender_id,
                observed_at_wall_s=time.time(),
                observed_at_monotonic_s=time.monotonic(),
            )

        return wrapped

    dispatcher.register(MessageType.JOIN_REQUEST, _with_direct_observation(join_handler))
    dispatcher.register(MessageType.PEER_LIST, _with_direct_observation(peer_list_handler))
    dispatcher.register(MessageType.PING, ping_handler)
    dispatcher.register(MessageType.PONG, pong_handler)

    if state_worker is not None:
        dispatcher.register(
            MessageType.SENSOR_UPDATE,
            _with_direct_observation(
                make_sensor_update_handler(
                    state_worker=state_worker,
                    self_node_id=self_node_id,
                    peer_table=peer_table,
                    source_classifier=sensor_update_source_classifier,
                    on_seq_observed=sensor_update_seq_observer,
                )
            ),
        )
    else:
        dispatcher.register(
            MessageType.SENSOR_UPDATE,
            _with_direct_observation(handle_sensor_update),
        )

    dispatcher.register(
        MessageType.GOSSIP_STATE,
        _with_direct_observation(
            make_gossip_state_handler(
                peer_table=peer_table,
                self_node_id=self_node_id,
                on_peer_discovered=on_peer_discovered,
            )
        ),
    )
    if state_worker is not None:
        dispatcher.register(
            MessageType.FULL_SYNC_REQUEST,
            _with_direct_observation(
                make_full_sync_request_handler(
                    state_worker=state_worker,
                    peer_table=peer_table,
                    send=send_function,
                    self_node_id=self_node_id,
                )
            ),
        )
        dispatcher.register(
            MessageType.FULL_SYNC_RESPONSE,
            _with_direct_observation(
                make_full_sync_response_handler(
                    state_worker=state_worker,
                    peer_table=peer_table,
                    self_node_id=self_node_id,
                    on_peer_discovered=on_peer_discovered,
                )
            ),
        )
    else:
        dispatcher.register(
            MessageType.FULL_SYNC_REQUEST,
            _with_direct_observation(handle_full_sync_request),
        )
        dispatcher.register(
            MessageType.FULL_SYNC_RESPONSE,
            _with_direct_observation(handle_full_sync_response),
        )
    dispatcher.register(
        MessageType.DELTA_UNAVAILABLE,
        _with_direct_observation(
            make_delta_unavailable_handler(
                send=send_function,
                self_node_id=self_node_id,
            )
        ),
    )
    if state_worker is not None:
        dispatcher.register(
            MessageType.GET_DELTA,
            _with_direct_observation(
                make_get_delta_handler(
                    state_worker=state_worker,
                    send=send_function,
                    self_node_id=self_node_id,
                )
            ),
        )
    else:
        dispatcher.register(
            MessageType.GET_DELTA,
            _with_direct_observation(handle_get_delta),
        )
    dispatcher.register(MessageType.ERROR, _handle_error)
    dispatcher.register(MessageType.ACK, _handle_ack)
    return dispatcher, peer_table


def _handle_error(msg: object) -> None:
    """Log an inbound protocol ``ERROR`` message without crashing dispatch."""
    if not isinstance(msg, Message):
        return
    log = get_logger(__name__, msg.sender_id)
    payload = msg.payload
    if isinstance(payload, ErrorPayload):
        log.warning(
            "Protocol ERROR received: "
            f"sender={msg.sender_id} reason={payload.reason}"
        )
        return
    log.warning(f"Protocol ERROR received with invalid payload from {msg.sender_id}")


def _handle_ack(msg: object) -> None:
    """Log an inbound protocol ``ACK`` message without crashing dispatch."""
    if not isinstance(msg, Message):
        return
    log = get_logger(__name__, msg.sender_id)
    payload = msg.payload
    if isinstance(payload, AckPayload):
        log.debug(
            "Protocol ACK received: "
            f"sender={msg.sender_id} acked_type={payload.acked_type}"
        )
        return
    log.warning(f"Protocol ACK received with invalid payload from {msg.sender_id}")
