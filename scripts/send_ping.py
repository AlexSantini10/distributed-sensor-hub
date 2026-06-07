"""Send a manual PING message to a locally running node for smoke testing."""

import sys
import time
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from networking.tcp_client import TcpClient, Peer
from protocol.factory import build_ping

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
