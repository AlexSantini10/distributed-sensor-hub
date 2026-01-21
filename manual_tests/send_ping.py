# Requires node.py to be running
from networking.tcp_client import TcpClient, Peer
from protocol.message import Message
from protocol.message_types import MessageType
import time

client = TcpClient()

peer = Peer(
    node_id="node-1",
    host="127.0.0.1",
    port=9000,
)

client.add_peer(peer)

msg = Message(
    msg_type=MessageType.PING,
    sender_id="client-test",
    payload={"timestamp": int(time.time() * 1000)},
)

client.send_json(peer.node_id, msg)

time.sleep(0.5)
client.stop()
