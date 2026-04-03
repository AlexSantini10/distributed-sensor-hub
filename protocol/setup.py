"""Assemble protocol routing and handler bindings for a runtime node.

Responsibilities:
    - Build the dispatcher used to route validated inbound messages.
    - Create the shared membership table consumed by membership handlers.
    - Register handlers for membership, liveness, replication, and control flows.
"""

from typing import Any, Callable, Optional, Tuple

from protocol.dispatcher import MessageDispatcher
from protocol.message_types import MessageType
from protocol import handlers

from membership.peer import Peer as MembershipPeer
from membership.peer_table import PeerTable
from membership.handlers import make_membership_handlers


OnPeerDiscovered = Callable[[MembershipPeer], None]


def setup_protocol(
	self_node_id: str,
	send_function: Any,
	state_worker: Any = None,
	on_peer_discovered: Optional[OnPeerDiscovered] = None,
) -> Tuple[MessageDispatcher, PeerTable]:
	"""Build the protocol dispatcher and register message handlers.

	Membership messages are delegated to the membership subsystem, while
	``SENSOR_UPDATE`` can be bound to a state worker so replicated updates are
	merged locally. The returned peer table is the membership view owned by the
	node and updated by membership handlers as peers are discovered or announced.

	Args:
		self_node_id (str): Identifier of the local node.
		send_function (Any): Callable used by handlers to emit outbound protocol messages.
		state_worker (Any): Optional state merge component for ``SENSOR_UPDATE`` handling.
		on_peer_discovered (Optional[OnPeerDiscovered]): Optional callback invoked
		when membership discovers a new peer.

	Returns:
		Tuple[MessageDispatcher, PeerTable]: Configured dispatcher and the peer
		table used by membership handlers.
	"""
	dispatcher = MessageDispatcher()

	peer_table = PeerTable(self_node_id=self_node_id)

	join_handler, peer_list_handler = make_membership_handlers(
		peer_table=peer_table,
		send=send_function,
		self_node_id=self_node_id,
		on_peer_discovered=on_peer_discovered,
	)

	dispatcher.register(MessageType.JOIN_REQUEST, join_handler)
	dispatcher.register(MessageType.PEER_LIST, peer_list_handler)

	dispatcher.register(MessageType.PING, handlers.handle_ping)
	dispatcher.register(MessageType.PONG, handlers.handle_pong)

	if state_worker is not None:
		sensor_update_handler = handlers.make_sensor_update_handler(
			state_worker=state_worker,
			self_node_id=self_node_id,
		)
		dispatcher.register(MessageType.SENSOR_UPDATE, sensor_update_handler)
	else:
		dispatcher.register(MessageType.SENSOR_UPDATE, handlers.handle_sensor_update)

	dispatcher.register(MessageType.GOSSIP_STATE, handlers.handle_gossip_state)

	dispatcher.register(MessageType.FULL_SYNC_REQUEST, handlers.handle_full_sync_request)
	dispatcher.register(MessageType.FULL_SYNC_RESPONSE, handlers.handle_full_sync_response)

	dispatcher.register(MessageType.ERROR, handlers.handle_error)
	dispatcher.register(MessageType.ACK, handlers.handle_ack)

	return dispatcher, peer_table
