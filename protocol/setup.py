"""Assemble protocol routing and handler bindings for a runtime node."""

from collections.abc import Callable

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
from utils.typing import SenderLike, StateWorkerLike


OnPeerDiscovered = Callable[[MembershipPeer], None]


def setup_protocol(
    self_node_id: str,
    send_function: SenderLike,
    state_worker: StateWorkerLike | None = None,
    on_peer_discovered: OnPeerDiscovered | None = None,
    phi_threshold_suspect: float = 3.0,
    phi_threshold_dead: float = 8.0,
    phi_initial_interval_s: float = 1.0,
) -> tuple[MessageDispatcher, PeerTable]:
    """Build the protocol dispatcher and register message handlers."""
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

    dispatcher.register(MessageType.JOIN_REQUEST, join_handler)
    dispatcher.register(MessageType.PEER_LIST, peer_list_handler)
    dispatcher.register(MessageType.PING, ping_handler)
    dispatcher.register(MessageType.PONG, pong_handler)

    if state_worker is not None:
        dispatcher.register(
            MessageType.SENSOR_UPDATE,
            make_sensor_update_handler(
                state_worker=state_worker,
                self_node_id=self_node_id,
            ),
        )
    else:
        dispatcher.register(MessageType.SENSOR_UPDATE, handle_sensor_update)

    dispatcher.register(
        MessageType.GOSSIP_STATE,
        make_gossip_state_handler(
            peer_table=peer_table,
            self_node_id=self_node_id,
            on_peer_discovered=on_peer_discovered,
        ),
    )
    if state_worker is not None:
        dispatcher.register(
            MessageType.FULL_SYNC_REQUEST,
            make_full_sync_request_handler(
                state_worker=state_worker,
                peer_table=peer_table,
                send=send_function,
                self_node_id=self_node_id,
            ),
        )
        dispatcher.register(
            MessageType.FULL_SYNC_RESPONSE,
            make_full_sync_response_handler(
                state_worker=state_worker,
                peer_table=peer_table,
                self_node_id=self_node_id,
                on_peer_discovered=on_peer_discovered,
            ),
        )
    else:
        dispatcher.register(MessageType.FULL_SYNC_REQUEST, handle_full_sync_request)
        dispatcher.register(MessageType.FULL_SYNC_RESPONSE, handle_full_sync_response)
    dispatcher.register(
        MessageType.DELTA_UNAVAILABLE,
        make_delta_unavailable_handler(
            send=send_function,
            self_node_id=self_node_id,
        ),
    )
    if state_worker is not None:
        dispatcher.register(
            MessageType.GET_DELTA,
            make_get_delta_handler(
                state_worker=state_worker,
                send=send_function,
                self_node_id=self_node_id,
            ),
        )
    else:
        dispatcher.register(MessageType.GET_DELTA, handle_get_delta)
    dispatcher.register(MessageType.ERROR, _handle_error)
    dispatcher.register(MessageType.ACK, _handle_ack)
    return dispatcher, peer_table


def _handle_error(_msg: object) -> None:
    """Reject processing of an unimplemented protocol error message."""
    raise NotImplementedError("ERROR not implemented yet")


def _handle_ack(_msg: object) -> None:
    """Reject processing of an unimplemented acknowledgement message."""
    raise NotImplementedError("ACK not implemented yet")
