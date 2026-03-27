"""Networking and membership bootstrap helpers."""

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
	"""Runtime networking bundle."""

	client: TcpClient
	server: object
	dispatcher: object
	peer_table: object
	bootstrap_peers: List[TcpPeer]


def make_join_request(self_node_id: str, host: str, port: int) -> Message:
	"""Build a JOIN_REQUEST message for membership bootstrap."""
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
	"""Send JOIN_REQUEST to configured bootstrap peers."""
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

	A peer may bind to 0.0.0.0 locally, but that address is not usable as
	a remote destination. In containerized environments, the node identifier
	is often also the DNS-resolvable service name.
	"""
	if advertised_host == "0.0.0.0":
		return node_id

	return advertised_host


class ClientPeerRegistry:
	"""Track outbound client peers and avoid duplicate registrations."""

	def __init__(self, client: TcpClient):
		"""Initialize the registry."""
		self._client = client
		self._known_peer_ids = set()
		self._lock = threading.Lock()

	def ensure_peer(self, node_id: str, host: str, port: int) -> None:
		"""Ensure that the TCP client can send to the specified peer."""
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
	"""Register configured bootstrap peers into the TCP client."""
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
	"""Insert bootstrap peers into membership as a best-effort seed."""
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
	"""Create client, protocol dispatcher, membership callbacks, and server."""
	client = TcpClient()
	registry = ClientPeerRegistry(client=client)

	def on_peer_discovered(peer: MembershipPeer) -> None:
		"""Handle runtime discovery of a new peer."""
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