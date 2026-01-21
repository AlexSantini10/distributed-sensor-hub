import socket
import struct
import threading

from networking.tcp_server import TcpServer
from protocol.message import Message
from protocol.message_types import MessageType


class DummyDispatcher:
    def __init__(self):
        self._event = threading.Event()
        self.messages = []

    def dispatch(self, msg) -> None:
        self.messages.append(msg)
        self._event.set()

    def wait(self, timeout_s: float) -> bool:
        return self._event.wait(timeout_s)


def _send_frame(host: str, port: int, payload: bytes) -> None:
    frame = struct.pack(">I", len(payload)) + payload
    with socket.create_connection((host, port), timeout=2.0) as s:
        s.sendall(frame)


def test_tcp_server_dispatches_message(tmp_path):
    host = "127.0.0.1"
    port = 0

    dispatcher = DummyDispatcher()

    server = TcpServer(
        host=host,
        port=port,
        dispatcher=dispatcher,
        recv_timeout_s=0.2,
        accept_timeout_s=0.2,
    )

    server.start()
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        msg = Message(
            msg_type=MessageType.PING,
            sender_id="node-1",
            payload={"timestamp": 123},
        )

        _send_frame(host, bound_port, msg.to_bytes())

        assert dispatcher.wait(2.0) is True
        assert len(dispatcher.messages) == 1
        assert dispatcher.messages[0].msg_type == MessageType.PING
    finally:
        server.stop()
