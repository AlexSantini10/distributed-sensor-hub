"""Maintain outbound framed TCP transport for peer-to-peer messaging.

Responsibilities:
    - Keep one best-effort outbound connection per known peer.
    - Serialize protocol messages into framed payloads suitable for transport.
    - Preserve per-peer FIFO enqueue order while a connection remains healthy.
    - Retry connection establishment with bounded backoff after failures.
"""

from __future__ import annotations

import json
import queue
import selectors
import socket
import struct
import threading
import time
from dataclasses import dataclass

from utils.typing import JsonValue, SupportsToBytes


@dataclass(frozen=True)
class Peer:
    """Describe a remote node addressable by the outbound transport.

    Attributes:
        node_id (str): Stable identifier used to route messages to the peer worker.
        host (str): IPv4 address or hostname used for the TCP connection target.
        port (int): TCP port exposed by the peer server.
    """

    node_id: str
    host: str
    port: int


class TcpClient:
    """Maintain persistent outbound TCP sessions to known peers.

    Attributes:
        _connect_timeout_s (float): Connection-establishment timeout in seconds.
        _send_timeout_s (float): Send operation timeout in seconds.
        _max_frame_size (int): Maximum allowed payload size before framing.
        _backoff_initial_s (float): Initial reconnect delay in seconds.
        _backoff_max_s (float): Upper bound for reconnect delay in seconds.
        _backoff_mode (str): Backoff strategy name, either linear or exponential.
        _idle_check_interval_s (float): Interval for idle connection liveness checks.
        _tcp_keepalive (bool): Whether OS-level TCP keepalive is enabled.
        _stop_event (threading.Event): Shared shutdown signal for all peer workers.
        _lock (threading.Lock): Synchronizes access to the worker registry.
        _workers (dict[str, _PeerWorker]): Active outbound workers keyed by peer node ID.
    """

    def __init__(
        self,
        connect_timeout_s: float = 2.0,
        send_timeout_s: float = 2.0,
        max_frame_size: int = 1024 * 1024,
        backoff_initial_s: float = 0.5,
        backoff_max_s: float = 10.0,
        backoff_mode: str = "exponential",
        idle_check_interval_s: float = 1.0,
        tcp_keepalive: bool = True,
    ) -> None:
        """Initialize the outbound transport manager.

        Args:
            connect_timeout_s (float): Maximum time allowed for a TCP connect attempt.
            send_timeout_s (float): Maximum time allowed for a framed send operation.
            max_frame_size (int): Maximum payload size, in bytes, before rejection.
            backoff_initial_s (float): Initial reconnect delay after a failure.
            backoff_max_s (float): Maximum reconnect delay.
            backoff_mode (str): Reconnect growth policy, typically exponential.
            idle_check_interval_s (float): Delay between idle-side liveness probes.
            tcp_keepalive (bool): Enables socket keepalive when supported.

        Returns:
            None: This initializer configures the outbound transport manager.
        """
        self._connect_timeout_s = connect_timeout_s
        self._send_timeout_s = send_timeout_s
        self._max_frame_size = max_frame_size

        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s
        self._backoff_mode = backoff_mode

        self._idle_check_interval_s = idle_check_interval_s
        self._tcp_keepalive = tcp_keepalive

        self._stop_event = threading.Event()

        self._lock = threading.Lock()
        self._workers: dict[str, _PeerWorker] = {}
        self._stopped = False

    def add_peer(self, peer: Peer) -> None:
        """Register a peer and start maintaining its outbound connection.

        Args:
            peer (Peer): Peer descriptor identifying the remote node and endpoint.

        Returns:
            None

        Raises:
            RuntimeError: If a worker already exists for ``peer.node_id``.
        """
        with self._lock:
            if self._stopped or self._stop_event.is_set():
                raise RuntimeError("TcpClient is stopped")
            if peer.node_id in self._workers:
                raise RuntimeError(f"Peer already exists: {peer.node_id}")

            worker = _PeerWorker(
                peer=peer,
                stop_event=self._stop_event,
                connect_timeout_s=self._connect_timeout_s,
                send_timeout_s=self._send_timeout_s,
                max_frame_size=self._max_frame_size,
                backoff_initial_s=self._backoff_initial_s,
                backoff_max_s=self._backoff_max_s,
                backoff_mode=self._backoff_mode,
                idle_check_interval_s=self._idle_check_interval_s,
                tcp_keepalive=self._tcp_keepalive,
            )
            self._workers[peer.node_id] = worker
            worker.start()

    def remove_peer(self, peer_id: str) -> None:
        """Remove a peer worker and discard unsent queued messages.

        Args:
            peer_id (str): Node identifier of the peer to remove.

        Returns:
            None
        """
        with self._lock:
            worker = self._workers.pop(peer_id, None)

        if worker is not None:
            worker.stop()

    def send_json(self, peer_id: str, obj: SupportsToBytes | JsonValue) -> None:
        """Enqueue a message for best-effort delivery to a peer.

        Messages are serialized immediately and delivered in FIFO order per
        peer if the underlying connection remains healthy. The transport may
        drop queued or in-flight messages across disconnects, so callers must
        rely on protocol-level idempotency for gossip or replicated-state
        exchanges.

        Args:
            peer_id (str): Node identifier of the destination peer.
            obj (SupportsToBytes | JsonValue): JSON-serializable object or value
                exposing ``to_bytes()``.

        Returns:
            None

        Raises:
            KeyError: If ``peer_id`` is not registered.
            TypeError: If ``obj`` cannot be serialized into bytes.
            ValueError: If the serialized payload exceeds ``_max_frame_size``.
        """
        worker = self._get_worker(peer_id)
        payload = _serialize_to_json_bytes(obj)
        if len(payload) > self._max_frame_size:
            raise ValueError("payload exceeds maximum frame size")
        worker.enqueue(payload)

    def stop(self) -> None:
        """Stop all peer workers and close their sockets.

        Returns:
            None
        """
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._stop_event.set()
            workers = list(self._workers.values())
            self._workers.clear()

        for w in workers:
            w.stop()

    def _get_worker(self, peer_id: str) -> "_PeerWorker":
        """Resolve the worker responsible for a peer.

        Args:
            peer_id (str): Node identifier of the destination peer.

        Returns:
            _PeerWorker: Worker assigned to the peer.

        Raises:
            KeyError: If the peer is unknown.
        """
        with self._lock:
            worker = self._workers.get(peer_id)
        if worker is None:
            raise KeyError(f"Unknown peer_id: {peer_id}")
        return worker


def _serialize_to_json_bytes(obj: SupportsToBytes | JsonValue) -> bytes:
    """Serialize a message object into transport payload bytes.

    The serializer accepts protocol message objects that already define their
    wire encoding through ``to_bytes()`` as well as plain JSON-compatible
    values. This keeps message-format ownership in the protocol layer.

    Args:
        obj (SupportsToBytes | JsonValue): Value to serialize for transport.

    Returns:
        bytes: UTF-8 JSON bytes or protocol-defined binary bytes.

    Raises:
        TypeError: If ``to_bytes()`` returns a non-bytes value or if ``obj``
            is not JSON serializable.
    """
    if isinstance(obj, SupportsToBytes):
        raw = obj.to_bytes()
        return raw

    try:
        return json.dumps(obj).encode("utf-8")
    except TypeError as exc:
        raise TypeError(f"Object is not JSON serializable: {type(obj)}") from exc


class _PeerWorker:
    """Own a single outbound peer connection and its send queue.

    Attributes:
        _peer (Peer): Remote peer served by this worker.
        _stop_event (threading.Event): Global stop signal shared by the client.
        _connect_timeout_s (float): Timeout applied to connection attempts.
        _send_timeout_s (float): Timeout applied to send operations.
        _max_frame_size (int): Maximum permitted payload size.
        _backoff_initial_s (float): Initial reconnect delay.
        _backoff_max_s (float): Maximum reconnect delay.
        _backoff_mode (str): Backoff policy name.
        _idle_check_interval_s (float): Delay between idle liveness checks.
        _tcp_keepalive (bool): Whether keepalive is enabled on created sockets.
        _queue (queue.Queue[bytes]): FIFO queue of serialized payloads awaiting transmission.
        _sock_lock (threading.Lock): Synchronizes socket replacement and shutdown.
        _sock (socket.socket | None): Active socket or None when disconnected.
        _thread (threading.Thread): Background thread running the worker loop.
        _local_stop (threading.Event): Per-worker shutdown signal.
    """

    def __init__(
        self,
        peer: Peer,
        stop_event: threading.Event,
        connect_timeout_s: float,
        send_timeout_s: float,
        max_frame_size: int,
        backoff_initial_s: float,
        backoff_max_s: float,
        backoff_mode: str,
        idle_check_interval_s: float,
        tcp_keepalive: bool,
    ):
        """Initialize a worker for a single remote peer.

        Args:
            peer (Peer): Remote peer descriptor.
            stop_event (threading.Event): Shared client-wide stop signal.
            connect_timeout_s (float): Timeout for connection attempts.
            send_timeout_s (float): Timeout for socket send operations.
            max_frame_size (int): Maximum permitted payload size.
            backoff_initial_s (float): Initial reconnect delay.
            backoff_max_s (float): Maximum reconnect delay.
            backoff_mode (str): Backoff policy name.
            idle_check_interval_s (float): Delay between idle liveness checks.
            tcp_keepalive (bool): Enables keepalive on created sockets.

        Returns:
            None: This initializer configures the peer worker state.
        """
        self._peer = peer
        self._stop_event = stop_event

        self._connect_timeout_s = connect_timeout_s
        self._send_timeout_s = send_timeout_s
        self._max_frame_size = max_frame_size

        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s
        self._backoff_mode = backoff_mode
        self._idle_check_interval_s = idle_check_interval_s
        self._tcp_keepalive = tcp_keepalive

        self._queue: queue.Queue[bytes] = queue.Queue()
        self._sock_lock = threading.Lock()
        self._sock: socket.socket | None = None

        self._thread = threading.Thread(
            target=self._run,
            name=f"tcp-peer-{peer.node_id}",
            daemon=True,
        )

        self._local_stop = threading.Event()

    def start(self) -> None:
        """Start the worker thread.

        Returns:
            None
        """
        self._thread.start()

    def stop(self) -> None:
        """Stop the worker, close its socket, and drop queued payloads.

        Returns:
            None
        """
        self._local_stop.set()
        self._close_socket()
        self._thread.join(timeout=5.0)

        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def enqueue(self, payload: bytes) -> None:
        """Append a serialized payload to the peer FIFO queue.

        Args:
            payload (bytes): Serialized message bytes without the length prefix.

        Returns:
            None
        """
        self._queue.put(payload)

    def _run(self) -> None:
        """Maintain the connection lifecycle and drain queued payloads.

        Returns:
            None
        """
        backoff_s = self._backoff_initial_s

        while not self._should_stop():
            if self._sock is None:
                if not self._connect():
                    self._sleep_backoff(backoff_s)
                    backoff_s = self._next_backoff(backoff_s)
                    continue
                backoff_s = self._backoff_initial_s

            if not self._drain_send_queue_once():
                self._close_socket()
                continue

            if self._queue.empty():
                if self._detect_server_closed():
                    self._close_socket()
                    continue

                self._sleep_interruptible(self._idle_check_interval_s)

    def _should_stop(self) -> bool:
        """Report whether the worker should terminate.

        Returns:
            bool: ``True`` when either the global or local stop signal is set.
        """
        return self._stop_event.is_set() or self._local_stop.is_set()

    def _connect(self) -> bool:
        """Establish a TCP connection to the assigned peer.

        Returns:
            bool: ``True`` if the socket is connected and installed.
        """
        if self._should_stop():
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout_s)

        if self._tcp_keepalive:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

        try:
            sock.connect((self._peer.host, self._peer.port))
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            return False

        sock.settimeout(self._send_timeout_s)

        install_socket = False
        with self._sock_lock:
            if not self._should_stop():
                self._sock = sock
                install_socket = True

        if not install_socket:
            try:
                sock.close()
            except OSError:
                pass
            return False

        return True

    def _drain_send_queue_once(self) -> bool:
        """Send queued payloads until the queue empties or the socket fails.

        Returns:
            bool: ``True`` if the connection remains usable after draining,
            otherwise ``False``.
        """
        while not self._should_stop():
            try:
                payload = self._queue.get_nowait()
            except queue.Empty:
                return True

            ok = self._send_frame(payload)
            if not ok:
                return False

        return True

    def _send_frame(self, payload: bytes) -> bool:
        """Send one length-prefixed payload to the peer.

        Args:
            payload (bytes): Serialized message bytes without the frame header.

        Returns:
            bool: ``True`` if the frame is sent or intentionally skipped,
            otherwise ``False`` when the connection appears broken.
        """
        if len(payload) > self._max_frame_size:
            return True

        frame = struct.pack(">I", len(payload)) + payload

        sock = self._get_socket()
        if sock is None:
            return False

        try:
            sock.sendall(frame)
            return True
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return False

    def _detect_server_closed(self) -> bool:
        """Probe whether the remote server has closed an idle connection.

        Returns:
            bool: ``True`` if the peer appears closed or unusable.
        """
        sock = self._get_socket()
        if sock is None:
            return True

        try:
            sel = selectors.DefaultSelector()
            try:
                sel.register(sock, selectors.EVENT_READ)
                events = sel.select(timeout=0.0)
                if not events:
                    return False

                data = sock.recv(1, socket.MSG_PEEK)
                return data == b""
            finally:
                try:
                    sel.close()
                except Exception:
                    pass
        except (ConnectionResetError, OSError):
            return True

    def _get_socket(self) -> socket.socket | None:
        """Return the current socket snapshot for this worker.

        Returns:
            socket.socket | None: Active socket or ``None`` if disconnected.
        """
        with self._sock_lock:
            return self._sock

    def _close_socket(self) -> None:
        """Close and clear the active socket reference.

        Returns:
            None
        """
        with self._sock_lock:
            sock = self._sock
            self._sock = None

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _sleep_backoff(self, backoff_s: float) -> None:
        """Sleep for a reconnect backoff interval unless interrupted.

        Args:
            backoff_s (float): Delay in seconds.

        Returns:
            None
        """
        self._sleep_interruptible(backoff_s)

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep in short increments so shutdown can preempt the delay.

        Args:
            seconds (float): Maximum time to sleep.

        Returns:
            None
        """
        end = time.time() + seconds
        while time.time() < end and not self._should_stop():
            time.sleep(0.05)

    def _next_backoff(self, current: float) -> float:
        """Compute the next reconnect delay.

        Args:
            current (float): Current backoff delay in seconds.

        Returns:
            float: Next bounded backoff delay.
        """
        if self._backoff_mode == "linear":
            nxt = current + self._backoff_initial_s
        else:
            nxt = current * 2.0

        if nxt > self._backoff_max_s:
            nxt = self._backoff_max_s
        return nxt
