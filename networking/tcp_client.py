import json
import queue
import selectors
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Peer:
    node_id: str
    host: str
    port: int


class TcpClient:
    """
    TCP client maintaining outgoing connections to known peers.

    Per-peer responsibilities (one thread per peer):
    - Keep a TCP connection alive.
    - Reconnect on failure with backoff.
    - Send queued messages in FIFO order (best-effort ordering).
    - Detect server-side closure even when idle.

    Public API:
    - add_peer(peer), remove_peer(peer_id)
    - send_json(peer_id, obj)
    - stop()
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
    ):
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

    def add_peer(self, peer: Peer) -> None:
        """
        Start maintaining a persistent outgoing connection to a peer.

        If a worker already exists for the same peer_id, this raises.
        """
        with self._lock:
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
        """
        Stop maintaining the connection to a peer and drop any queued messages.
        """
        with self._lock:
            worker = self._workers.pop(peer_id, None)

        if worker is not None:
            worker.stop()

    def send_json(self, peer_id: str, obj: Any) -> None:
        """
        Thread-safe, non-blocking enqueue of a JSON-serializable object.

        Ordering guarantee:
        - FIFO ordering is preserved per peer across enqueues.
        - Best-effort: messages may be lost on disconnect/reconnect, but
          the client will not reorder messages that it successfully sends.

        Raises:
        - KeyError if peer is unknown.
        - TypeError if obj is not JSON serializable (or message-like).
        """
        worker = self._get_worker(peer_id)
        payload = _serialize_to_json_bytes(obj)
        if len(payload) > self._max_frame_size:
            raise ValueError("payload exceeds maximum frame size")
        worker.enqueue(payload)

    def stop(self) -> None:
        """
        Stop all reconnect loops and close all sockets.
        """
        self._stop_event.set()

        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()

        for w in workers:
            w.stop()

    def _get_worker(self, peer_id: str) -> "_PeerWorker":
        with self._lock:
            worker = self._workers.get(peer_id)
        if worker is None:
            raise KeyError(f"Unknown peer_id: {peer_id}")
        return worker


def _serialize_to_json_bytes(obj: Any) -> bytes:
    """
    Serialize to JSON UTF-8 bytes.

    Supports:
    - Objects exposing to_bytes() -> bytes (e.g. your Message class)
    - dict / list / primitives JSON-serializable
    """
    to_bytes = getattr(obj, "to_bytes", None)
    if callable(to_bytes):
        raw = to_bytes()
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError("to_bytes() must return bytes")
        return bytes(raw)

    try:
        return json.dumps(obj).encode("utf-8")
    except TypeError as exc:
        raise TypeError(f"Object is not JSON serializable: {type(obj)}") from exc


class _PeerWorker:
    """
    Background thread maintaining a single peer connection and a send queue.
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
        self._sock: Optional[socket.socket] = None

        self._thread = threading.Thread(
            target=self._run,
            name=f"tcp-peer-{peer.node_id}",
            daemon=True,
        )

        self._local_stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """
        Stop this worker and close its socket. Drops any queued messages.
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
        """
        Enqueue a raw JSON payload (already UTF-8 bytes).
        """
        self._queue.put(payload)

    def _run(self) -> None:
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
        return self._stop_event.is_set() or self._local_stop.is_set()

    def _connect(self) -> bool:
        """
        Establish a TCP connection to the peer. Returns True on success.
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

        with self._sock_lock:
            if self._should_stop():
                try:
                    sock.close()
                except OSError:
                    pass
                return False
            self._sock = sock

        return True

    def _drain_send_queue_once(self) -> bool:
        """
        Attempt to send queued messages until the queue is empty or a send fails.

        Returns True if still connected and no send failure occurred.
        Returns False if the connection appears broken.
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
        """
        Send one length-prefixed frame. Returns False on broken connection.
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
        """
        Best-effort detection of server-side closure while idle.

        Uses a selector to check readability; if readable, we peek 1 byte.
        If peek returns b"", the peer closed the connection.

        Returns True if the server side is considered closed.
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

    def _get_socket(self) -> Optional[socket.socket]:
        with self._sock_lock:
            return self._sock

    def _close_socket(self) -> None:
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
        self._sleep_interruptible(backoff_s)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end and not self._should_stop():
            time.sleep(0.05)

    def _next_backoff(self, current: float) -> float:
        if self._backoff_mode == "linear":
            nxt = current + self._backoff_initial_s
        else:
            nxt = current * 2.0

        if nxt > self._backoff_max_s:
            nxt = self._backoff_max_s
        return nxt
