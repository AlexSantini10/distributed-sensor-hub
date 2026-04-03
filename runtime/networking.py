"""Assemble runtime networking and membership bootstrap behavior.

Responsibilities:
    Build the transport and protocol stack used by a node at runtime.
    Convert configured bootstrap addresses into an initial membership seed.
    Send join messages and register newly discovered peers so gossip and state
    dissemination can converge across the cluster.
"""

import threading
from dataclasses import dataclass
from typing import Callable, List, Tuple

from protocol.message import Message
from protocol.message_types import MessageType
from protocol.setup import setup_protocol

from networking.tcp_client import Peer as TcpPeer
from networking.tcp_client import TcpClient

from membership.peer import Peer as MembershipPeer


@dataclass(frozen=True)
class NetworkingContext:
	"""Bundle the networking objects required by the runtime.

	Attributes:
		client: Outbound TCP client used to send protocol messages to peers.
		server: Inbound server that accepts and dispatches protocol messages.
		dispatcher: Protocol dispatcher that routes decoded messages to handlers.
		peer_table: Membership view updated by protocol handlers and gossip.
		bootstrap_peers: Configured peers available for initial cluster contact.
	"""

	client: TcpClient
	server: object
	dispatcher: object
	peer_table: object
	bootstrap_peers: List[TcpPeer]


def make_join_request(self_node_id: str, host: str, port: int) -> Message:
	"""Build a membership `JOIN_REQUEST` message.

	Args:
		self_node_id: Stable identifier of the local node.
		host: Advertised host that peers should use for future connections.
		port: Advertised TCP port that peers should use for future connections.

	Returns:
		Message: Protocol message announcing the local node's reachable endpoint.
	"""
	return Message(
		msg_type=MessageType.JOIN_REQUEST,
		sender_id=self_node_id,
		payload={
			"node_id": self_node_id,
			"host": host,
			"port": port,
		},
	)


def bootstrap_membership(
	self_node_id: str,
	host: str,
	port: int,
	peers: List[TcpPeer],
	send: Callable[[str, Message], None],
	log,
) -> None:
	"""Send `JOIN_REQUEST` messages to configured bootstrap peers.

	Args:
		self_node_id: Stable identifier of the local node.
		host: Advertised host for the local node.
		port: Advertised TCP port for the local node.
		peers: Bootstrap peers that should receive the initial join attempt.
		send: Function that transmits a protocol message to a peer by node ID.
		log: Logger used for membership bootstrap diagnostics.

	Raises:
		No exception is propagated. Individual send failures are logged and the
		remaining peers are still attempted.
	"""
	join_msg = make_join_request(
		self_node_id=self_node_id,
		host=host,
		port=port,
	)

	for peer in peers:
		try:
			send(peer.node_id, join_msg)
			log.info(f"Sent JOIN_REQUEST to {peer.host}:{peer.port}")
		except Exception:
			log.error(
				f"JOIN_REQUEST failed to {peer.host}:{peer.port}",
				exc_info=True,
			)


def resolve_peer_host(node_id: str, advertised_host: str) -> str:
	"""Resolve a connectable host from an advertised endpoint.

	Args:
		node_id: Peer identifier, which may also be a routable service name.
		advertised_host: Host value advertised by the peer.

	Returns:
		str: Host value suitable for outbound connections.

	A peer may bind to `0.0.0.0` locally, but that address is not usable as a
	remote destination. When that occurs, the node ID is treated as the
	connectable address contract for peer-to-peer traffic.
	"""
	if advertised_host == "0.0.0.0":
		return node_id

	return advertised_host


class ClientPeerRegistry:
	"""Track outbound client peers and suppress duplicate registrations.

	Attributes:
		_client: TCP client that owns the outbound peer list.
		_known_peer_ids: Set of peer identifiers already registered locally.
		_lock: Mutex guarding concurrent peer discovery updates.
	"""

	def __init__(self, client: TcpClient):
		"""Initialize the registry.

		Args:
			client: TCP client that should learn about discovered peers.
		"""
		self._client = client
		self._known_peer_ids = set()
		self._lock = threading.Lock()

	def ensure_peer(self, node_id: str, host: str, port: int) -> None:
		"""Register a peer with the outbound client if it is not known yet.

		Args:
			node_id: Stable identifier of the peer.
			host: Advertised host for the peer.
			port: Advertised TCP port for the peer.

		Raises:
			No exception is propagated. Duplicate-registration races are treated
			as benign and absorbed.
		"""
		with self._lock:
			if node_id in self._known_peer_ids:
				return

		connect_host = resolve_peer_host(node_id=node_id, advertised_host=host)

		try:
			self._client.add_peer(
				TcpPeer(
					node_id=node_id,
					host=connect_host,
					port=port,
				)
			)
		except RuntimeError:
			pass

		with self._lock:
			self._known_peer_ids.add(node_id)


def build_bootstrap_peers(bootstrap_peers: List[Tuple[str, int]], client: TcpClient) -> List[TcpPeer]:
	"""Register configured bootstrap peers with the outbound client.

	Args:
		bootstrap_peers: Host and port pairs configured for initial cluster
			contact.
		client: TCP client that should be able to send to bootstrap peers.

	Returns:
		List[TcpPeer]: Peer descriptors representing the configured bootstrap
		targets.
	"""
	registered_peers = []

	for host, port in bootstrap_peers:
		peer_id = f"bootstrap@{host}:{port}"
		peer = TcpPeer(node_id=peer_id, host=host, port=port)

		try:
			client.add_peer(peer)
		except RuntimeError:
			pass

		registered_peers.append(peer)

	return registered_peers


def seed_peer_table(peer_table, bootstrap_peers: List[TcpPeer], log) -> None:
	"""Insert bootstrap peers into membership as a best-effort seed.

	Args:
		peer_table: Membership table consumed by gossip and message routing.
		bootstrap_peers: Peers that should appear in the initial membership view.
		log: Logger used for best-effort seeding diagnostics.

	Raises:
		No exception is propagated. Seeding failures are logged and ignored so
		active bootstrap can still proceed.
	"""
	for peer in bootstrap_peers:
		try:
			peer_table.add_peer(
				MembershipPeer.new(
					node_id=peer.node_id,
					host=peer.host,
					port=peer.port,
				)
			)
		except Exception:
			log.warning("Failed to seed bootstrap peer into PeerTable", exc_info=True)


def setup_node_networking(
	config,
	log,
	state_worker,
	tcp_server_cls,
) -> NetworkingContext:
	"""Create the runtime networking stack for a node.

	Args:
		config: Runtime configuration containing node identity, bind address, and
			configured bootstrap peers.
		log: Logger used for networking diagnostics.
		state_worker: State worker used by protocol handlers to apply updates and
			serve snapshots.
		tcp_server_cls: Server class used to bind inbound transport.

	Returns:
		NetworkingContext: Fully assembled networking objects for the runtime.
	"""
	client = TcpClient()
	registry = ClientPeerRegistry(client=client)

	def on_peer_discovered(peer: MembershipPeer) -> None:
		"""Register a discovered peer and actively initiate reciprocal join.

		Args:
			peer: Membership entry discovered through gossip or join handling.

		The follow-up `JOIN_REQUEST` reduces dependence on passive gossip by
		prompting the new peer to learn the local node's advertised endpoint.
		"""
		registry.ensure_peer(peer.node_id, peer.host, peer.port)

		join_msg = make_join_request(
			self_node_id=config.node_id,
			host=config.host,
			port=config.port,
		)

		try:
			client.send_json(peer.node_id, join_msg)
			log.info(
				f"Discovery JOIN_REQUEST sent to {peer.node_id} "
				f"{peer.host}:{peer.port}"
			)
		except Exception:
			log.warning(
				f"Discovery JOIN_REQUEST failed to {peer.node_id} "
				f"{peer.host}:{peer.port}",
				exc_info=True,
			)

	bootstrap_peers = build_bootstrap_peers(
		bootstrap_peers=config.bootstrap_peers,
		client=client,
	)

	dispatcher, peer_table = setup_protocol(
		self_node_id=config.node_id,
		send_function=client.send_json,
		state_worker=state_worker,
		on_peer_discovered=on_peer_discovered,
	)

	server = tcp_server_cls(
		host=config.host,
		port=config.port,
		dispatcher=dispatcher,
	)

	return NetworkingContext(
		client=client,
		server=server,
		dispatcher=dispatcher,
		peer_table=peer_table,
		bootstrap_peers=bootstrap_peers,
	)
