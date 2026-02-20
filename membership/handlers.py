# membership/handlers.py
from typing import Callable, Optional

from protocol.message import Message
from protocol.message_types import MessageType
from membership.peer import Peer
from membership.peer_table import PeerTable
from utils.logging import get_logger


Sender = Callable[[str, Message], None]
OnPeerDiscovered = Callable[[Peer], None]
# Sender(peer_id, message) -> send to that peer


def make_membership_handlers(
	peer_table: PeerTable,
	send: Sender,
	self_node_id: str,
	on_peer_discovered: Optional[OnPeerDiscovered] = None,
):
	"""
	Factory returning JOIN_REQUEST and PEER_LIST handlers
	bound to a specific PeerTable, sender, and optional discovery callback.

	on_peer_discovered(peer) is called only when a peer is newly added to the PeerTable.
	"""
	log = get_logger(__name__, self_node_id)

	def _notify_discovered(peer: Peer) -> None:
		if on_peer_discovered is None:
			return
		try:
			on_peer_discovered(peer)
		except Exception:
			log.warning(
				f"on_peer_discovered failed for peer {peer.node_id} {peer.host}:{peer.port}",
				exc_info=True,
			)

	def handle_join_request(msg: Message) -> None:
		payload = msg.payload

		node_id = payload.get("node_id")
		host = payload.get("host")
		port = payload.get("port")

		if not node_id or not host or not isinstance(port, int):
			log.warning("Invalid JOIN_REQUEST payload")
			return

		# Ignore self-join completely (no side effects)
		if node_id == self_node_id:
			return

		peer = Peer.new(node_id=node_id, host=host, port=port)
		added = peer_table.add_peer(peer)

		if added:
			log.info(f"New peer joined: {node_id} {host}:{port}")
			_notify_discovered(peer)
		else:
			log.info(f"JOIN_REQUEST from known peer: {node_id}")

		peers_payload = [
			{
				"node_id": p.node_id,
				"host": p.host,
				"port": p.port,
			}
			for p in peer_table.list_peers()
		]

		reply = Message(
			msg_type=MessageType.PEER_LIST,
			sender_id=self_node_id,
			payload={"peers": peers_payload},
		)

		# Reply to transport-level sender, not logical node_id
		send(msg.sender_id, reply)

	def handle_peer_list(msg: Message) -> None:
		payload = msg.payload
		peers = payload.get("peers")

		if not isinstance(peers, list):
			log.warning("Invalid PEER_LIST payload")
			return

		added_count = 0

		for entry in peers:
			node_id = entry.get("node_id")
			host = entry.get("host")
			port = entry.get("port")

			if not node_id or not host or not isinstance(port, int):
				continue

			if node_id == self_node_id:
				continue

			peer = Peer.new(node_id=node_id, host=host, port=port)
			if peer_table.add_peer(peer):
				added_count += 1
				_notify_discovered(peer)

		if added_count > 0:
			log.info(f"Integrated {added_count} new peers from PEER_LIST")

	return handle_join_request, handle_peer_list