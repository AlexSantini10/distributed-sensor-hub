import threading

from networking.tcp_server import TcpServer
from networking.tcp_client import TcpClient, Peer
from protocol.message import Message
from protocol.message_types import MessageType


class DummyDispatcher:
    """
    Dispatcher used for integration testing.

    Records received messages and allows the test
    to wait until a message arrives.
    """

    def __init__(self):
        self.messages = []
        self._event = threading.Event()

    def dispatch(self, msg) -> None:
        self.messages.append(msg)
        self._event.set()

    def wait(self, timeout_s: float) -> bool:
        return self._event.wait(timeout_s)


def test_server_receives_message_from_tcp_client():
    host = "127.0.0.1"
    port = 0  # let OS choose a free port

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

        # Wait for the dispatcher to receive the message
        assert dispatcher.wait(2.0) is True
        assert len(dispatcher.messages) == 1

        received = dispatcher.messages[0]
        assert received.msg_type == MessageType.PING
        assert received.sender_id == "client-1"
        assert received.payload["timestamp"] == 123

    finally:
        client.stop()
        server.stop()
