from typing import Tuple

from protocol.dispatcher import MessageDispatcher
from protocol.message_types import MessageType
from protocol import handlers

from membership.peer_table import PeerTable
from membership.handlers import make_membership_handlers


def setup_protocol(
    self_node_id: str,
    send_function,
) -> Tuple[MessageDispatcher, PeerTable]:
    """
    Setup protocol dispatcher and register all message handlers.

    The PeerTable (membership state) is owned by the node and
    injected into the handlers via closures.
    """
    dispatcher = MessageDispatcher()

    # Membership state owned by the node
    peer_table = PeerTable(self_node_id=self_node_id)

    # Create membership handlers bound to local state
    join_handler, peer_list_handler = make_membership_handlers(
        peer_table=peer_table,
        send=send_function,
        self_node_id=self_node_id,
    )

    # Membership
    dispatcher.register(MessageType.JOIN_REQUEST, join_handler)
    dispatcher.register(MessageType.PEER_LIST, peer_list_handler)

    # Other protocol handlers (still mostly unimplemented)
    dispatcher.register(MessageType.PING, handlers.handle_ping)
    dispatcher.register(MessageType.PONG, handlers.handle_pong)

    dispatcher.register(MessageType.SENSOR_UPDATE, handlers.handle_sensor_update)
    dispatcher.register(MessageType.GOSSIP_STATE, handlers.handle_gossip_state)

    dispatcher.register(
        MessageType.FULL_SYNC_REQUEST,
        handlers.handle_full_sync_request,
    )
    dispatcher.register(
        MessageType.FULL_SYNC_RESPONSE,
        handlers.handle_full_sync_response,
    )

    dispatcher.register(MessageType.ERROR, handlers.handle_error)
    dispatcher.register(MessageType.ACK, handlers.handle_ack)

    return dispatcher, peer_table
