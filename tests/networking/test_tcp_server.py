"""Validate TCP server framing and dispatch behavior.

Responsibilities:
    - Send a manually framed message to the TCP server.
    - Assert that the server decodes and dispatches the payload once.
"""

import socket
import struct
import threading

from networking.tcp_server import TcpServer
from protocol.message import Message
from protocol.message_types import MessageType


class DummyDispatcher:
    """Capture server-dispatched messages for assertions.

    Attributes:
        _event (threading.Event): Signal set when a message is dispatched.
        messages (list[Message]): Ordered list of dispatched messages.
    """

    def __init__(self) -> None:
        """Initialize an empty dispatch capture buffer.

        Returns:
            None: This constructor does not return a value.
        """
        self._event = threading.Event()
        self.messages: list[Message] = []

    def dispatch(self, msg: Message) -> None:
        """Record one dispatched message and release waiters.

        Args:
            msg (Message): Decoded protocol message delivered by the server.

        Returns:
            None: This method appends to the capture buffer.
        """
        self.messages.append(msg)
        self._event.set()

    def wait(self, timeout_s: float) -> bool:
        """Wait for at least one dispatch event.

        Args:
            timeout_s (float): Maximum wait time in seconds.

        Returns:
            bool: ``True`` if a message arrived before timeout.
        """
        return self._event.wait(timeout_s)


def _send_frame(host: str, port: int, payload: bytes) -> None:
    """Send one length-prefixed payload to the TCP server.

    Args:
        host (str): Target server host.
        port (int): Target server port.
        payload (bytes): Raw encoded protocol message.

    Returns:
        None: This helper performs the network send in place.

    Raises:
        OSError: If the socket cannot connect or send the frame.
    """
    frame = struct.pack(">I", len(payload)) + payload
    with socket.create_connection((host, port), timeout=2.0) as s:
        s.sendall(frame)


def test_tcp_server_dispatches_message() -> None:
    """Assert that the TCP server dispatches one received framed message.

    Returns:
        None: This test asserts server dispatch behavior.
    """
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
