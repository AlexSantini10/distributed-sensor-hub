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
from networking.tcp_client import TcpClient, Peer

from sensors.sensor_manager import SensorManager
from state.node_state_worker import NodeStateWorker
from webapi.http_api import WebAPIServer

# --------------------------------------------------

load_dotenv()


def bootstrap(self_node_id: str, host: str, port: int, peers, send, log) -> None:
	join_msg = Message(
		msg_type=MessageType.JOIN_REQUEST,
		sender_id=self_node_id,
		payload={
			"node_id": self_node_id,
			"host": host,
			"port": port,
		},
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

	# --------------------------------------------------
	# Networking: client + server
	# --------------------------------------------------
	client = TcpClient()

	bootstrap_peers = []
	for host, port in config.bootstrap_peers:
		peer = Peer(
			node_id=f"bootstrap@{host}:{port}",
			host=host,
			port=port,
		)
		client.add_peer(peer)
		bootstrap_peers.append(peer)

	try:
		dispatcher, peer_table = setup_protocol(
			self_node_id=config.node_id,
			send_function=client.send_json,
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
	sensor_event_queue = Queue()

	try:
		sensor_manager = SensorManager(callback=sensor_event_queue.put)
		sensor_manager.load_from_env()
		sensor_manager.start_all()
		log.info(f"Started {len(sensor_manager.sensors)} sensors")
	except Exception:
		log.critical("Failed to initialize sensors", exc_info=True)
		raise

	# --------------------------------------------------
	# State worker (LWW)
	# --------------------------------------------------
	state_worker = NodeStateWorker(
		node_id=config.node_id,
		event_queue=sensor_event_queue,
		log=log,
	)
	state_worker.start()
	log.info("State worker started")

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

		try:
			sensor_manager.stop_all()
		except Exception:
			log.error("Error while stopping sensors", exc_info=True)

		try:
			state_worker.stop()
		except Exception:
			log.error("Error while stopping state worker", exc_info=True)

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
