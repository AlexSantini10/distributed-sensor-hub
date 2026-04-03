"""Membership protocol handlers for peer discovery exchanges.

Responsibilities:
- Build message handlers bound to a specific peer table and send primitive.
- Process join requests as best-effort membership advertisements.
- Integrate peer-list gossip replies idempotently.
- Notify the runtime when membership learns previously unknown peers.

The handlers implement additive membership only: they discover peers and
refresh local knowledge, but they do not remove peers or resolve conflicting
address records.
"""

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
	"""Create handlers for join and peer-list membership messages.

	Args:
		peer_table: Shared membership table updated by both handlers.
		send: Transport callback used to send protocol messages to a peer ID.
		self_node_id: Logical identifier of the local node.
		on_peer_discovered: Optional callback invoked only when a previously
			unknown peer is inserted into `peer_table`.

	Returns:
		tuple[Callable[[Message], None], Callable[[Message], None]]: A pair of
		handlers for `JOIN_REQUEST` and `PEER_LIST` messages.
	"""
	log = get_logger(__name__, self_node_id)

	def _notify_discovered(peer: Peer) -> None:
		"""Invoke the discovery callback for a newly learned peer.

		Args:
			peer: Peer that was inserted into the membership table.

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
			msg: Incoming `JOIN_REQUEST` message whose payload must contain
				`node_id`, `host`, and `port`.

		Returns:
			None: The handler updates membership state and may emit a reply.

		Notes:
			The handler treats repeated join requests as idempotent advertisements.
			It replies to `msg.sender_id`, which is the transport-level sender,
			rather than the logical `node_id` declared in the payload.
		"""
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
		"""Merge peers from a peer-list message into local membership state.

		Args:
			msg: Incoming `PEER_LIST` message whose payload must contain a
				`peers` list of dictionaries with `node_id`, `host`, and `port`.

		Returns:
			None: The handler updates membership state in place.

		Notes:
			This merge is additive and idempotent. Existing peers are retained,
			invalid entries are skipped, and self entries are ignored. The message
			format carries network coordinates only and does not attempt LWW-style
			reconciliation of peer metadata.
		"""
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
