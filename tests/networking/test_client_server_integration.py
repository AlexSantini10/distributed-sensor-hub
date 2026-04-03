"""Validate end-to-end TCP client and server interoperability.

Responsibilities:
    - Start a real TCP server and connect with the project TCP client.
    - Assert framed protocol messages are dispatched without corruption.
"""

import threading
from networking.tcp_client import Peer, TcpClient
from networking.tcp_server import TcpServer
from protocol.message import Message
from protocol.message_types import MessageType


class DummyDispatcher:
    """Capture dispatched protocol messages for integration assertions.

    Attributes:
        messages (list): Ordered list of dispatched protocol messages.
        _event (threading.Event): Signal set when at least one message arrives.
    """

    def __init__(self) -> None:
        """Initialize an empty dispatch capture buffer.

        Returns:
            None: This constructor does not return a value.
        """
        self.messages = []
        self._event = threading.Event()

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
        """Wait for at least one message to be dispatched.

        Args:
            timeout_s (float): Maximum wait time in seconds.

        Returns:
            bool: ``True`` if a message arrived before the timeout.
        """
        return self._event.wait(timeout_s)


def test_server_receives_message_from_tcp_client() -> None:
    """Assert that a TCP client can send a framed protocol message to the server.

    Returns:
        None: This test asserts client-server interoperability.
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

        client = TcpClient(
            connect_timeout_s=1.0,
            send_timeout_s=1.0,
            backoff_initial_s=0.1,
            backoff_max_s=0.5,
        )

        peer = Peer(
            node_id="server",
            host=host,
            port=bound_port,
        )

        client.add_peer(peer)

        msg = Message(
            msg_type=MessageType.PING,
            sender_id="client-1",
            payload={"timestamp": 123},
        )

        client.send_json(peer.node_id, msg)

        assert dispatcher.wait(2.0) is True
        assert len(dispatcher.messages) == 1

        received = dispatcher.messages[0]
        assert received.msg_type == MessageType.PING
        assert received.sender_id == "client-1"
        assert received.payload["timestamp"] == 123

    finally:
        client.stop()
        server.stop()
