"""Send a manual PING message to a locally running node for smoke testing."""

# Requires node.py to be running
from networking.tcp_client import TcpClient, Peer
from protocol.factory import build_ping
import time

client = TcpClient()

peer = Peer(
    node_id="node-1",
    host="127.0.0.1",
    port=9000,
)

client.add_peer(peer)

msg = build_ping(
    sender_id="client-test",
    ping_timestamp_ms=int(time.time() * 1000),
)

client.send_json(peer.node_id, msg)

time.sleep(0.5)
client.stop()
