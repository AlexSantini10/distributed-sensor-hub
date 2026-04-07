"""Assemble protocol routing and handler bindings for a runtime node.

Responsibilities:
    - Build the dispatcher used to route validated inbound messages.
    - Create the shared membership table consumed by membership handlers.
    - Register handlers for membership, liveness, replication, and control flows.
"""

from collections.abc import Callable

from fd.heartbeat import HeartbeatMonitor
from membership.handlers import make_membership_handlers
from membership.peer import Peer as MembershipPeer
from membership.peer_table import PeerTable
from protocol import handlers
from protocol.dispatcher import MessageDispatcher
from protocol.message_types import MessageType
from utils.typing import SenderLike, StateWorkerLike


OnPeerDiscovered = Callable[[MembershipPeer], None]


def setup_protocol(
    self_node_id: str,
    send_function: SenderLike,
    state_worker: StateWorkerLike | None = None,
    on_peer_discovered: OnPeerDiscovered | None = None,
) -> tuple[MessageDispatcher, PeerTable, HeartbeatMonitor]:
    """Build the protocol dispatcher and register message handlers.

    Membership messages are delegated to the membership subsystem, while
    ``SENSOR_UPDATE`` can be bound to a state worker so replicated updates are
    merged locally. The returned peer table is the membership view owned by the
    node and updated by membership handlers as peers are discovered or announced.

    Args:
        self_node_id (str): Identifier of the local node.
        send_function (SenderLike): Callable used by handlers to emit outbound
            protocol messages.
        state_worker (StateWorkerLike | None): Optional state merge component for
            ``SENSOR_UPDATE`` handling.
        on_peer_discovered (OnPeerDiscovered | None): Optional callback invoked
            when membership discovers a new peer.

    Returns:
        tuple[MessageDispatcher, PeerTable, HeartbeatMonitor]: Configured
            dispatcher, peer table, and heartbeat monitor used by liveness handlers.
    """
    dispatcher = MessageDispatcher()
    peer_table = PeerTable(self_node_id=self_node_id)
    heartbeat_monitor = HeartbeatMonitor()

    join_handler, peer_list_handler = make_membership_handlers(
        peer_table=peer_table,
        send=send_function,
        self_node_id=self_node_id,
        on_peer_discovered=on_peer_discovered,
    )

    ping_handler, pong_handler = handlers.make_heartbeat_handlers(
        peer_table=peer_table,
        send=send_function,
        self_node_id=self_node_id,
        heartbeat_monitor=heartbeat_monitor,
    )

    dispatcher.register(MessageType.JOIN_REQUEST, join_handler)
    dispatcher.register(MessageType.PEER_LIST, peer_list_handler)
    dispatcher.register(MessageType.PING, ping_handler)
    dispatcher.register(MessageType.PONG, pong_handler)

    if state_worker is not None:
        dispatcher.register(
            MessageType.SENSOR_UPDATE,
            handlers.make_sensor_update_handler(
                state_worker=state_worker,
                self_node_id=self_node_id,
            ),
        )
    else:
        dispatcher.register(MessageType.SENSOR_UPDATE, handlers.handle_sensor_update)

    dispatcher.register(MessageType.GOSSIP_STATE, handlers.handle_gossip_state)
    if state_worker is not None:
        dispatcher.register(
            MessageType.FULL_SYNC_REQUEST,
            handlers.make_full_sync_request_handler(
                state_worker=state_worker,
                peer_table=peer_table,
                send=send_function,
                self_node_id=self_node_id,
            ),
        )
        dispatcher.register(
            MessageType.FULL_SYNC_RESPONSE,
            handlers.make_full_sync_response_handler(
                state_worker=state_worker,
                peer_table=peer_table,
                self_node_id=self_node_id,
                on_peer_discovered=on_peer_discovered,
            ),
        )
    else:
        dispatcher.register(MessageType.FULL_SYNC_REQUEST, handlers.handle_full_sync_request)
        dispatcher.register(MessageType.FULL_SYNC_RESPONSE, handlers.handle_full_sync_response)
    dispatcher.register(
        MessageType.DELTA_UNAVAILABLE,
        handlers.make_delta_unavailable_handler(
            send=send_function,
            self_node_id=self_node_id,
        ),
    )
    dispatcher.register(MessageType.ERROR, handlers.handle_error)
    dispatcher.register(MessageType.ACK, handlers.handle_ack)
    return dispatcher, peer_table, heartbeat_monitor
