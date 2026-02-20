# node.py
import os
import sys
import time
import logging
import threading
from queue import Queue
from dotenv import load_dotenv

# --------------------------------------------------
# Bootstrap logging (active immediately)
# --------------------------------------------------

def setup_bootstrap_logging():
	logging.basicConfig(
		level=logging.DEBUG,
		format="%(asctime)s | %(levelname)s | BOOTSTRAP | %(message)s",
		stream=sys.stderr,
	)

setup_bootstrap_logging()
_bootstrap_log = logging.getLogger("bootstrap")


def global_exception_hook(exc_type, exc, tb):
	_bootstrap_log.critical(
		"UNHANDLED EXCEPTION",
		exc_info=(exc_type, exc, tb),
	)

sys.excepthook = global_exception_hook


def thread_exception_hook(args):
	_bootstrap_log.critical(
		f"UNHANDLED THREAD EXCEPTION in thread {args.thread.name}",
		exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
	)

threading.excepthook = thread_exception_hook

# --------------------------------------------------
# Imports (after bootstrap logging)
# --------------------------------------------------

from utils.config import load_config
from utils.logging import setup_logging, get_logger

from protocol.setup import setup_protocol
from protocol.message import Message
from protocol.message_types import MessageType

from networking.tcp_server import TcpServer
from networking.tcp_client import TcpClient, Peer as TcpPeer

from membership.peer import Peer as MembershipPeer

from sensors.sensor_manager import SensorManager
from state.node_state_worker import NodeStateWorker
from state.sensor_update_publisher import SensorUpdatePublisher
from webapi.http_api import WebAPIServer

# --------------------------------------------------

load_dotenv()


def _make_join_request(self_node_id: str, host: str, port: int) -> Message:
	return Message(
		msg_type=MessageType.JOIN_REQUEST,
		sender_id=self_node_id,
		payload={
			"node_id": self_node_id,
			"host": host,
			"port": port,
		},
	)


def bootstrap(self_node_id: str, host: str, port: int, peers, send, log) -> None:
	join_msg = _make_join_request(self_node_id=self_node_id, host=host, port=port)

	for peer in peers:
		try:
			send(peer.node_id, join_msg)
			log.info(f"Sent JOIN_REQUEST to {peer.host}:{peer.port}")
		except Exception:
			log.error(
				f"JOIN_REQUEST failed to {peer.host}:{peer.port}",
				exc_info=True,
			)


def main():
	_bootstrap_log.info("Node process starting")

	# --------------------------------------------------
	# Load configuration
	# --------------------------------------------------
	try:
		config = load_config()
	except Exception:
		_bootstrap_log.critical("Failed to load configuration", exc_info=True)
		raise

	# --------------------------------------------------
	# Optional log cleanup
	# --------------------------------------------------
	clear_log = os.getenv("CLEAR_LOG", "false").lower() == "true"
	if clear_log and config.log_file:
		try:
			with open(config.log_file, "w"):
				pass
		except OSError:
			_bootstrap_log.error(
				f"Failed to clear log file {config.log_file}",
				exc_info=True,
			)

	# --------------------------------------------------
	# Full logging setup
	# --------------------------------------------------
	try:
		setup_logging(config.node_id, config.log_level, config.log_file)
	except Exception:
		_bootstrap_log.critical("Failed to setup logging", exc_info=True)
		raise

	log = get_logger(__name__, config.node_id)
	log.info("Full logging initialized")

	# Predeclare optional subsystems for safe cleanup
	sensor_manager = None
	publisher = None
	web_api = None

	# --------------------------------------------------
	# State (LWW) - start early
	# --------------------------------------------------
	sensor_event_queue = Queue()

	state_worker = NodeStateWorker(
		node_id=config.node_id,
		event_queue=sensor_event_queue,
		log=log,
	)
	state_worker.start()
	log.info("State worker started")

	# --------------------------------------------------
	# Networking: client + server
	# --------------------------------------------------
	client = TcpClient()

	# Keep track of which peer_ids are already added to TcpClient
	known_client_peers = set()
	client_lock = threading.Lock()

	def _ensure_client_peer(node_id: str, host: str, port: int) -> None:
		with client_lock:
			if node_id in known_client_peers:
				return

		try_host = host
		# If peer advertised bind-all, it's not connectable from other containers.
		# In Docker networks, the service/container DNS name is usually the node_id.
		if try_host == "0.0.0.0":
			try_host = node_id

		try:
			client.add_peer(TcpPeer(node_id=node_id, host=try_host, port=port))
		except RuntimeError:
			pass

		with client_lock:
			known_client_peers.add(node_id)

	def on_peer_discovered(peer: MembershipPeer) -> None:
		"""
		Called when membership learns a new peer at runtime.
		Ensures we can send to it and accelerates convergence via JOIN_REQUEST.
		"""
		_ensure_client_peer(peer.node_id, peer.host, peer.port)

		join_msg = _make_join_request(
			self_node_id=config.node_id,
			host=config.host,
			port=config.port,
		)
		try:
			client.send_json(peer.node_id, join_msg)
			log.info(f"Discovery JOIN_REQUEST sent to {peer.node_id} {peer.host}:{peer.port}")
		except Exception:
			log.warning(
				f"Discovery JOIN_REQUEST failed to {peer.node_id} {peer.host}:{peer.port}",
				exc_info=True,
			)

	# Configure bootstrap peers (initial outbound connections)
	bootstrap_peers = []
	for host, port in config.bootstrap_peers:
		peer_id = f"bootstrap@{host}:{port}"
		try:
			client.add_peer(TcpPeer(node_id=peer_id, host=host, port=port))
		except RuntimeError:
			pass
		bootstrap_peers.append(TcpPeer(node_id=peer_id, host=host, port=port))

	try:
		dispatcher, peer_table = setup_protocol(
			self_node_id=config.node_id,
			send_function=client.send_json,
			state_worker=state_worker,
			on_peer_discovered=on_peer_discovered,
		)
	except Exception:
		log.critical("Failed to setup protocol", exc_info=True)
		raise

	server = TcpServer(
		host=config.host,
		port=config.port,
		dispatcher=dispatcher,
	)

	try:
		server.start()
	except Exception:
		log.critical("Failed to start TCP server", exc_info=True)
		raise

	log.info(f"Node listening on {config.host}:{config.port}")

	# --------------------------------------------------
	# Seed membership with bootstrap peers (best-effort)
	# --------------------------------------------------
	for bp in bootstrap_peers:
		try:
			peer_table.add_peer(
				MembershipPeer.new(
					node_id=bp.node_id,
					host=bp.host,
					port=bp.port,
				)
			)
		except Exception:
			log.warning("Failed to seed bootstrap peer into PeerTable", exc_info=True)

	# --------------------------------------------------
	# Bootstrap membership
	# --------------------------------------------------
	if bootstrap_peers:
		bootstrap(
			self_node_id=config.node_id,
			host=config.host,
			port=config.port,
			peers=bootstrap_peers,
			send=client.send_json,
			log=log,
		)
	else:
		log.info("No bootstrap peers configured")

	# --------------------------------------------------
	# Sensor subsystem
	# --------------------------------------------------
	try:
		sensor_manager = SensorManager(callback=sensor_event_queue.put)
		sensor_manager.load_from_env()
		sensor_manager.start_all()
		log.info(f"Started {len(sensor_manager.sensors)} sensors")

		publisher = SensorUpdatePublisher(
			self_node_id=config.node_id,
			peer_table=peer_table,
			tcp_client=client,
			state_worker=state_worker,
			log=log,
		)
		publisher.start()
		log.info("Sensor update publisher started")

	except Exception:
		log.critical("Failed to initialize sensors", exc_info=True)
		raise

	# --------------------------------------------------
	# Web API (safe version)
	# --------------------------------------------------
	web_api_port = int(os.getenv("WEB_API_PORT", str(config.port + 1000)))

	try:
		log.info(f"Starting WebAPI on {config.host}:{web_api_port}")
		web_api = WebAPIServer(
			host=config.host,
			port=web_api_port,
			state_provider=state_worker.get_state_snapshot,
			updates_provider=state_worker.get_updates_snapshot,
			log=log,
		)
		web_api.start()
		log.info("WebAPI started")
	except Exception:
		log.critical("Failed to start WebAPI", exc_info=True)
		raise

	# --------------------------------------------------
	# Main loop
	# --------------------------------------------------
	try:
		while True:
			time.sleep(1)

	except KeyboardInterrupt:
		log.info("Node shutting down (KeyboardInterrupt)")

	except Exception:
		log.critical("Unhandled exception in main loop", exc_info=True)

	finally:
		log.info("Node cleanup started")

		if publisher is not None:
			try:
				publisher.stop()
			except Exception:
				log.error("Error while stopping publisher", exc_info=True)

		if sensor_manager is not None:
			try:
				sensor_manager.stop_all()
			except Exception:
				log.error("Error while stopping sensors", exc_info=True)

		try:
			state_worker.stop()
		except Exception:
			log.error("Error while stopping state worker", exc_info=True)

		if web_api is not None:
			try:
				web_api.stop()
			except Exception:
				log.error("Error while stopping WebAPI", exc_info=True)

		try:
			server.stop()
			client.stop()
		except Exception:
			log.error("Error while stopping networking", exc_info=True)

		log.info("Node shutdown complete")


if __name__ == "__main__":
	main()