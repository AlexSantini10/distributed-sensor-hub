import time
from dotenv import load_dotenv

from utils.config import load_config
from utils.logging import setup_logging, get_logger

from protocol.setup import setup_protocol
from protocol.message import Message
from protocol.message_types import MessageType

from networking.tcp_server import TcpServer
from networking.tcp_client import TcpClient, Peer

load_dotenv()


def bootstrap(self_node_id: str, host: str, port: int, peers, send, log) -> None:
    """
    Send JOIN_REQUEST to all bootstrap peers.

    Bootstrap peers are treated as network endpoints only.
    Their real node_id will be learned via JOIN/PEER_LIST.
    """
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
            log.debug(f"Sent JOIN_REQUEST to {peer.host}:{peer.port}")
        except Exception as exc:
            log.debug(f"Failed to send JOIN_REQUEST to {peer.host}:{peer.port}: {exc}")


def main():
    config = load_config()
    setup_logging(config.node_id, config.log_level, config.log_file)
    log = get_logger(__name__, config.node_id)

    # Outgoing connections manager
    client = TcpClient()

    # Register bootstrap peers (network endpoints only)
    bootstrap_peers = []
    for host, port in config.bootstrap_peers:
        peer = Peer(
            node_id=f"bootstrap@{host}:{port}",
            host=host,
            port=port,
        )
        client.add_peer(peer)
        bootstrap_peers.append(peer)

    # Setup protocol and membership
    dispatcher, peer_table = setup_protocol(
        self_node_id=config.node_id,
        send_function=client.send_json,
    )
    # peer_table intentionally kept for future FD/gossip

    server = TcpServer(
        host=config.host,
        port=config.port,
        dispatcher=dispatcher,
    )

    log.info("Node starting")
    log.info(f"Config loaded: host={config.host} port={config.port}")

    server.start()

    # Bootstrap membership
    bootstrap(
        self_node_id=config.node_id,
        host=config.host,
        port=config.port,
        peers=bootstrap_peers,
        send=client.send_json,
        log=log,
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Node shutting down")
        server.stop()
        client.stop()


if __name__ == "__main__":
    main()
