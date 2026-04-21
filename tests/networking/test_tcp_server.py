"""Validate TCP server framing and dispatch behavior.

Responsibilities:
    - Send a manually framed message to the TCP server.
    - Assert that the server decodes and dispatches the payload once.
"""

import socket
import struct
import threading
import time
from dataclasses import dataclass

import pytest
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


@dataclass
class BurstMetrics:
    """Aggregate metrics for bounded burst-style load tests."""

    completed: int
    successes: int
    errors: int
    rejected_connections: int
    avg_latency_ms: float
    p95_latency_ms: float
    throughput_msgs_per_s: float


def _p95(values: list[float]) -> float:
    """Return deterministic p95 for a non-empty sample list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95)))
    return ordered[idx]


def _run_ping_burst(
    *,
    host: str,
    port: int,
    total_clients: int,
    connect_timeout_s: float = 0.8,
    send_timeout_s: float = 0.8,
) -> BurstMetrics:
    """Run bounded concurrent clients and compute summary metrics."""
    start_barrier = threading.Barrier(total_clients + 1)
    timings_ms: list[float] = []
    timings_lock = threading.Lock()
    errors = 0
    errors_lock = threading.Lock()

    def worker(i: int) -> None:
        nonlocal errors
        payload = build_ping(sender_id=f"burst-{i}", ping_timestamp_ms=i).to_bytes()
        frame = struct.pack(">I", len(payload)) + payload
        try:
            start_barrier.wait(timeout=2.0)
            t0 = time.monotonic()
            with socket.create_connection((host, port), timeout=connect_timeout_s) as s:
                s.settimeout(send_timeout_s)
                s.sendall(frame)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            with timings_lock:
                timings_ms.append(elapsed_ms)
        except Exception:
            with errors_lock:
                errors += 1

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(total_clients)]
    for t in threads:
        t.start()
    start = time.monotonic()
    start_barrier.wait(timeout=2.0)
    for t in threads:
        t.join(timeout=3.0)
    elapsed_s = max(time.monotonic() - start, 1e-6)

    completed = sum(1 for t in threads if not t.is_alive())
    successes = len(timings_ms)
    throughput = successes / elapsed_s
    return BurstMetrics(
        completed=completed,
        successes=successes,
        errors=errors,
        rejected_connections=errors,
        avg_latency_ms=(sum(timings_ms) / successes) if successes else 0.0,
        p95_latency_ms=_p95(timings_ms),
        throughput_msgs_per_s=throughput,
    )


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


def test_tcp_server_load_many_concurrent_connections(caplog: pytest.LogCaptureFixture) -> None:
    """Measure bounded concurrent connection burst behavior."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.05,
        accept_timeout_s=0.05,
        max_connections=6,
        max_workers=6,
        backlog=8,
    )
    server.start()
    blockers: list[socket.socket] = []
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]
        # Pin connection slots to force explicit rejection path in a deterministic way.
        for _ in range(6):
            blocker = socket.create_connection((host, bound_port), timeout=1.0)
            blocker.settimeout(1.0)
            blockers.append(blocker)
        assert _wait_until(lambda: len(server._connections) == 6, timeout_s=2.0)

        with caplog.at_level("WARNING", logger="networking.tcp_server"):
            metrics = _run_ping_burst(host=host, port=bound_port, total_clients=24)

        rejected_by_log = sum(
            1
            for rec in caplog.records
            if "Connection rejected due to max_connections limit" in rec.getMessage()
        )
        assert metrics.completed == 24
        assert metrics.errors >= 0
        assert (rejected_by_log >= 1) or (metrics.errors >= 1)

        for blocker in blockers:
            blocker.close()
        blockers.clear()

        assert _wait_until(lambda: len(server._connections) == 0, timeout_s=2.0)

        # Server stays responsive after rejection pressure.
        health = _run_ping_burst(host=host, port=bound_port, total_clients=20)
        assert health.successes + health.errors == health.completed
        assert health.successes >= 8
        # CI runners can show noisy scheduling under concurrent socket bursts.
        # Keep a sanity floor for responsiveness, but avoid brittle perf gating.
        assert health.throughput_msgs_per_s > 10.0
        assert health.p95_latency_ms < 800.0
    finally:
        for blocker in blockers:
            blocker.close()
        server.stop()


def test_tcp_server_rejects_oversize_frame_and_stays_responsive() -> None:
    """Verify oversize frame is rejected and server remains healthy."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.05,
        accept_timeout_s=0.05,
        max_frame_size=128,
    )
    server.start()
    attacker: socket.socket | None = None
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]
        header = struct.pack(">I", 4096)
        attacker = socket.create_connection((host, bound_port), timeout=1.0)
        attacker.settimeout(1.0)
        attacker.sendall(header + (b"x" * 32))
        # Server should close oversize-frame connection.
        try:
            assert attacker.recv(1) == b""
        except ConnectionResetError:
            pass

        # Server should continue serving normal traffic afterward.
        valid = build_ping(sender_id="normal-after-oversize", ping_timestamp_ms=777)
        _send_frame(host, bound_port, valid.to_bytes())
        assert _wait_until(lambda: dispatcher.dispatched_count >= 1, timeout_s=2.0)
    finally:
        if attacker is not None:
            attacker.close()
        server.stop()


def test_tcp_server_slow_clients_and_fast_clients_latency() -> None:
    """Ensure slow clients do not starve fast traffic and collect latency stats."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.03,
        accept_timeout_s=0.03,
        max_connections=20,
        max_workers=10,
    )
    server.start()
    slow_threads: list[threading.Thread] = []
    slow_errors = 0
    fast_latencies_ms: list[float] = []
    lock = threading.Lock()
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        def slow_sender(i: int) -> None:
            nonlocal slow_errors
            payload = build_ping(sender_id=f"slow-{i}", ping_timestamp_ms=i).to_bytes()
            frame = struct.pack(">I", len(payload)) + payload
            try:
                with socket.create_connection((host, bound_port), timeout=1.0) as s:
                    s.settimeout(1.0)
                    for b in frame:
                        s.sendall(bytes([b]))
                        time.sleep(0.003)
            except Exception:
                with lock:
                    slow_errors += 1

        def fast_sender(i: int) -> None:
            payload = build_ping(sender_id=f"fast-{i}", ping_timestamp_ms=1000 + i).to_bytes()
            frame = struct.pack(">I", len(payload)) + payload
            t0 = time.monotonic()
            with socket.create_connection((host, bound_port), timeout=1.0) as s:
                s.settimeout(1.0)
                s.sendall(frame)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            with lock:
                fast_latencies_ms.append(elapsed_ms)

        for i in range(6):
            t = threading.Thread(target=slow_sender, args=(i,))
            slow_threads.append(t)
            t.start()

        fast_threads = [threading.Thread(target=fast_sender, args=(i,)) for i in range(24)]
        for t in fast_threads:
            t.start()
        for t in fast_threads:
            t.join(timeout=2.0)
        for t in slow_threads:
            t.join(timeout=3.0)

        assert _wait_until(lambda: dispatcher.dispatched_count >= 18, timeout_s=3.0)
        assert len(fast_latencies_ms) >= 20
        assert _p95(fast_latencies_ms) < 250.0
        assert (sum(fast_latencies_ms) / len(fast_latencies_ms)) < 120.0
        # Slow sender failures are tolerated only if bounded.
        assert slow_errors <= 2
    finally:
        server.stop()


def test_tcp_server_shutdown_during_active_traffic_is_clean() -> None:
    """Ensure concurrent stop under load finishes quickly and without leaks."""
    host = "127.0.0.1"
    dispatcher = DummyDispatcher()
    server = TcpServer(
        host=host,
        port=0,
        dispatcher=dispatcher,
        recv_timeout_s=0.03,
        accept_timeout_s=0.03,
        max_connections=24,
        max_workers=12,
    )
    server.start()
    stop_sending = threading.Event()
    sent_count = 0
    send_errors = 0
    send_lock = threading.Lock()
    try:
        assert server._server_sock is not None
        bound_port = server._server_sock.getsockname()[1]

        def traffic_worker(worker_id: int) -> None:
            nonlocal sent_count, send_errors
            seq = 0
            while not stop_sending.is_set():
                payload = build_ping(
                    sender_id=f"traffic-{worker_id}",
                    ping_timestamp_ms=worker_id * 10000 + seq,
                ).to_bytes()
                frame = struct.pack(">I", len(payload)) + payload
                try:
                    with socket.create_connection((host, bound_port), timeout=0.5) as s:
                        s.settimeout(0.5)
                        s.sendall(frame)
                    with send_lock:
                        sent_count += 1
                except OSError:
                    with send_lock:
                        send_errors += 1
                seq += 1
                time.sleep(0.002)

        senders = [threading.Thread(target=traffic_worker, args=(i,)) for i in range(8)]
        for t in senders:
            t.start()

        assert _wait_until(lambda: dispatcher.dispatched_count >= 20, timeout_s=3.0)
        t0 = time.monotonic()
        stop_thread = threading.Thread(target=server.stop)
        stop_thread.start()
        stop_thread.join(timeout=2.0)
        stop_elapsed = time.monotonic() - t0
        stop_sending.set()
        for t in senders:
            t.join(timeout=2.0)

        assert stop_thread.is_alive() is False
        assert stop_elapsed < 1.5
        assert server._accept_thread is None
        assert len(server._connections) == 0
        assert len(server._conn_futures) == 0
        assert sent_count > 0
        # Some errors after stop are expected, but should stay bounded.
        assert send_errors < sent_count + 30
    finally:
        stop_sending.set()
        server.stop()
