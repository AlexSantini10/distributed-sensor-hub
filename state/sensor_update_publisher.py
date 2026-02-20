# state/sensor_update_publisher.py
import threading

from protocol.message import Message
from protocol.message_types import MessageType


class SensorUpdatePublisher(threading.Thread):
	"""
	Publishes local-origin updates to all peers in peer_table.

	- Uses NodeStateWorker.pop_replication_updates() so it does not steal UI updates.
	- Filters out non-local origin to avoid re-broadcast loops for now.
	- Best-effort: if TcpClient does not know a peer_id, it adds it on the fly.
	"""

	def __init__(
		self,
		self_node_id: str,
		peer_table,
		tcp_client,
		state_worker,
		log,
		interval_s: float = 0.2,
	):
		super().__init__(daemon=True)

		self._self_node_id = self_node_id
		self._peer_table = peer_table
		self._client = tcp_client
		self._state_worker = state_worker
		self._log = log
		self._interval_s = interval_s

		self._stop_event = threading.Event()

	def stop(self) -> None:
		self._stop_event.set()

	def run(self) -> None:
		while not self._stop_event.is_set():
			try:
				self._publish_once()
			except Exception:
				self._log.error("SensorUpdatePublisher failed", exc_info=True)

			self._stop_event.wait(timeout=self._interval_s)

	def _publish_once(self) -> None:
		snapshot = self._state_worker.pop_replication_updates() or {}
		updates = snapshot.get(self._self_node_id, {}) or {}
		if not updates:
			return

		peers = self._peer_table.list_peers()
		if not peers:
			return

		for global_sensor_id, update in updates.items():
			origin = update.get("origin")
			if origin != self._self_node_id:
				continue

			sensor_id = global_sensor_id
			if isinstance(global_sensor_id, str) and ":" in global_sensor_id:
				sensor_id = global_sensor_id.split(":", 1)[1]

			msg = Message(
				msg_type=MessageType.SENSOR_UPDATE,
				sender_id=self._self_node_id,
				payload={
					"sensor_id": sensor_id,
					"value": update.get("value"),
					"ts_ms": update.get("ts_ms"),
					"origin": origin,
					"meta": update.get("meta", {}),
				},
			)

			for p in peers:
				self._send_to_peer(p, msg)

	def _send_to_peer(self, peer, msg: Message) -> None:
		try:
			self._client.send_json(peer.node_id, msg)
			return
		except KeyError:
			pass
		except Exception:
			self._log.warning(
				f"Failed to send SENSOR_UPDATE to peer_id={peer.node_id}",
				exc_info=True,
			)
			return

		try:
			from networking.tcp_client import Peer as TcpPeer

			tcp_peer = TcpPeer(node_id=peer.node_id, host=peer.host, port=peer.port)
			self._client.add_peer(tcp_peer)
			self._client.send_json(peer.node_id, msg)
		except Exception:
			self._log.warning(
				f"Failed to add/connect peer_id={peer.node_id} for SENSOR_UPDATE",
				exc_info=True,
			)