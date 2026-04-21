"""Validate TCP server framing and dispatch behavior.

Responsibilities:
    - Send a manually framed message to the TCP server.
    - Assert that the server decodes and dispatches the payload once.
"""

import socket
import struct
import threading
import time

from networking.tcp_server import TcpServer
from protocol.factory import build_ping
from protocol.message import Message


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
        self._lock = threading.Lock()
        self.messages: list[Message] = []
        self.dispatched_count = 0

    def dispatch(self, msg: Message) -> None:
        """Record one dispatched message and release waiters.

        Args:
            msg (Message): Decoded protocol message delivered by the server.

        Returns:
            None: This method appends to the capture buffer.
        """
        with self._lock:
            self.messages.append(msg)
            self.dispatched_count += 1
        self._event.set()

    def wait(self, timeout_s: float) -> bool:
        """Wait for at least one dispatch event.

        Args:
            timeout_s (float): Maximum wait time in seconds.

        Returns:
            bool: ``True`` if a message arrived before timeout.
        """
        return self._event.wait(timeout_s)


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.01) -> bool:
    """Poll a predicate until it returns ``True`` or timeout elapses.

    Args:
        predicate: Callable predicate to evaluate.
        timeout_s (float): Maximum wait in seconds.
        interval_s (float): Sleep interval between predicate checks.

    Returns:
        bool: ``True`` when predicate succeeds before timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


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

        msg = build_ping(sender_id="node-1", ping_timestamp_ms=123)

        _send_frame(host, bound_port, msg.to_bytes())

        assert dispatcher.wait(2.0) is True
        assert len(dispatcher.messages) == 1
        assert dispatcher.messages[0].msg_type.value == "PING"
    finally:
        server.stop()


def test_tcp_server_rejects_excess_connections() -> None:
    """Assert excess connections are rejected when max_connections is reached."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.1,
        accept_timeout_s=0.1,
        max_connections=1,
        max_workers=1,
    )
    server.start()
    first: socket.socket | None = None
    second: socket.socket | None = None
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        first = socket.create_connection((host, bound_port), timeout=1.0)
        assert _wait_until(lambda: len(server._connections) == 1, timeout_s=1.0)

        second = socket.create_connection((host, bound_port), timeout=1.0)
        second.settimeout(1.0)
        # Rejected connections should be closed quickly by the server.
        assert second.recv(1) == b""
        assert dispatcher.dispatched_count == 0
    finally:
        if second is not None:
            second.close()
        if first is not None:
            first.close()
        server.stop()


def test_tcp_server_slow_client_does_not_block_other_clients() -> None:
    """Assert a slow client does not block other clients from being served."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.05,
        accept_timeout_s=0.05,
        max_connections=8,
        max_workers=4,
    )
    server.start()
    slow: socket.socket | None = None
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        # Hold one connection open without sending a frame.
        slow = socket.create_connection((host, bound_port), timeout=1.0)
        slow.settimeout(1.0)

        msg = build_ping(sender_id="node-1", ping_timestamp_ms=321)
        _send_frame(host, bound_port, msg.to_bytes())

        assert dispatcher.wait(2.0) is True
        assert dispatcher.dispatched_count >= 1
    finally:
        if slow is not None:
            slow.close()
        server.stop()


def test_tcp_server_remains_responsive_under_burst() -> None:
    """Assert server remains responsive during many concurrent requests."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.1,
        accept_timeout_s=0.1,
        max_connections=12,
        max_workers=4,
    )
    server.start()
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        def send_one(index: int) -> None:
            msg = build_ping(sender_id=f"n-{index}", ping_timestamp_ms=index)
            _send_frame(host, bound_port, msg.to_bytes())

        threads = [threading.Thread(target=send_one, args=(idx,)) for idx in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        assert _wait_until(lambda: dispatcher.dispatched_count > 0, timeout_s=2.0)

        # Server should still accept and dispatch after the burst.
        msg = build_ping(sender_id="after-burst", ping_timestamp_ms=999)
        _send_frame(host, bound_port, msg.to_bytes())
        assert _wait_until(lambda: dispatcher.dispatched_count >= 2, timeout_s=2.0)
    finally:
        server.stop()


def test_tcp_server_stop_stops_accepting_new_connections() -> None:
    """Assert stop closes listeners and active connections cleanly."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.1,
        accept_timeout_s=0.1,
        max_connections=4,
        max_workers=2,
    )
    server.start()
    client: socket.socket | None = None
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]
        client = socket.create_connection((host, bound_port), timeout=1.0)
        client.settimeout(1.0)

        server.stop()
        assert server._accept_thread is None

        # Existing client should see server-side closure.
        try:
            assert client.recv(1) == b""
        except ConnectionResetError:
            # Linux often reports server-side close during shutdown as ECONNRESET.
            pass

        # New connections should be refused after shutdown.
        try:
            socket.create_connection((host, bound_port), timeout=0.2)
            raise AssertionError("Connection unexpectedly succeeded after server.stop()")
        except OSError:
            pass
    finally:
        if client is not None:
            client.close()
