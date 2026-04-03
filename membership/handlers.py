"""Handle membership messages used for peer discovery and convergence.

Responsibilities:
    - Build join and peer-list handlers bound to a shared membership table.
    - Apply additive, idempotent membership updates from bootstrap and gossip.
    - Reply with the local peer view so discovery can converge across nodes.
    - Notify runtime code when membership learns a previously unknown peer.
"""

from typing import Callable, Optional

from protocol.contracts import MembershipField
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
) -> tuple[Callable[[Message], None], Callable[[Message], None]]:
	"""Create handlers for join and peer-list membership messages.

	Args:
		peer_table (PeerTable): Shared membership table updated by both handlers.
		send (Sender): Transport callback used to send protocol messages to a peer ID.
		self_node_id (str): Logical identifier of the local node.
		on_peer_discovered (Optional[OnPeerDiscovered]): Optional callback invoked
		only when a previously unknown peer is inserted into ``peer_table``.

	Returns:
		tuple[Callable[[Message], None], Callable[[Message], None]]: Pair of
		handlers for ``JOIN_REQUEST`` and ``PEER_LIST`` messages.
	"""
	log = get_logger(__name__, self_node_id)

	def _notify_discovered(peer: Peer) -> None:
		"""Invoke the discovery callback for a newly learned peer.

		Args:
			peer (Peer): Peer that was inserted into the membership table.

		Returns:
			None: This helper emits side effects only through the callback.

		Raises:
			Exception: Any callback exception is caught internally and converted
			into a warning log entry.
		"""
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
		"""Process a join request and reply with the current peer list.

		Args:
			msg (Message): Incoming ``JOIN_REQUEST`` message whose payload must
			contain ``node_id``, ``host``, and ``port``.

		Returns:
			None: The handler updates membership state and may emit a reply.
		"""
		payload = msg.payload

		node_id = payload.get(MembershipField.NODE_ID.value)
		host = payload.get(MembershipField.HOST.value)
		port = payload.get(MembershipField.PORT.value)

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
				MembershipField.NODE_ID.value: p.node_id,
				MembershipField.HOST.value: p.host,
				MembershipField.PORT.value: p.port,
			}
			for p in peer_table.list_peers()
		]

		reply = Message(
			msg_type=MessageType.PEER_LIST,
			sender_id=self_node_id,
			payload={MembershipField.PEERS.value: peers_payload},
		)

		# Reply to transport-level sender, not logical node_id
		send(msg.sender_id, reply)

	def handle_peer_list(msg: Message) -> None:
		"""Merge peers from a peer-list message into local membership state.

		Args:
			msg (Message): Incoming ``PEER_LIST`` message whose payload must
			contain a ``peers`` list of dictionaries with ``node_id``, ``host``,
			and ``port``.

		Returns:
			None: The handler updates membership state in place.
		"""
		payload = msg.payload
		peers = payload.get(MembershipField.PEERS.value)

		if not isinstance(peers, list):
			log.warning("Invalid PEER_LIST payload")
			return

		added_count = 0

		for entry in peers:
			node_id = entry.get(MembershipField.NODE_ID.value)
			host = entry.get(MembershipField.HOST.value)
			port = entry.get(MembershipField.PORT.value)

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
