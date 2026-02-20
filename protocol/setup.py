# protocol/setup.py
from typing import Tuple

from protocol.dispatcher import MessageDispatcher
from protocol.message_types import MessageType
from protocol import handlers

from membership.peer_table import PeerTable
from membership.handlers import make_membership_handlers


def setup_protocol(
	self_node_id: str,
	send_function,
	state_worker=None,
) -> Tuple[MessageDispatcher, PeerTable]:
	"""
	Setup protocol dispatcher and register all message handlers.

	- PeerTable is owned by the node and injected into membership handlers.
	- state_worker is injected into SENSOR_UPDATE handling (if provided).
	"""
	dispatcher = MessageDispatcher()

	peer_table = PeerTable(self_node_id=self_node_id)

	join_handler, peer_list_handler = make_membership_handlers(
		peer_table=peer_table,
		send=send_function,
		self_node_id=self_node_id,
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