"""Accept inbound framed TCP messages and dispatch them to the protocol layer.

Responsibilities:
    - Bind a listening socket for node-to-node protocol traffic.
    - Read length-prefixed frames from each accepted connection.
    - Decode protocol envelopes and dispatch validated messages upstream.
    - Manage connection lifecycle and shutdown without interpreting message semantics.
"""

import socket
import struct
import threading
from types import TracebackType
from typing import Any, Optional, Protocol


class Dispatcher(Protocol):
    """Define the dispatch contract for decoded inbound messages.

    Attributes:
        None (None): This protocol defines behavior and no instance attributes.
    """

    def dispatch(self, msg: Any) -> None:
        """Handle a decoded protocol message.

        Args:
            msg (Any): Decoded message object produced by the protocol layer.

        Returns:
            None: This method forwards a decoded message to the protocol layer.
        """
        ...


class TcpServer:
    """Accept framed TCP messages and forward them to a dispatcher.

    Attributes:
        _host (str): Local interface address bound by the listening socket.
        _port (int): Local TCP port bound by the listening socket.
        _dispatcher (Dispatcher): Consumer of decoded protocol messages.
        _recv_timeout_s (float): Timeout for per-connection reads.
        _accept_timeout_s (float): Timeout for accept-loop wakeups.
        _max_frame_size (int): Upper bound for inbound frame payload size.
        _backlog (int): Kernel listen backlog for pending connections.
        _stop_event (threading.Event): Shared shutdown signal for server threads.
        _server_sock (Optional[socket.socket]): Listening socket, if started.
        _accept_thread (Optional[threading.Thread]): Thread running the accept loop, if started.
        _lock (threading.Lock): Synchronizes connection and thread tracking.
        _connections (set[socket.socket]): Active accepted sockets.
        _conn_threads (set[threading.Thread]): Active per-connection worker threads.
    """

    def __init__(
        self,
        host: str,
        port: int,
        dispatcher: Dispatcher,
        recv_timeout_s: float = 1.0,
        accept_timeout_s: float = 1.0,
        max_frame_size: int = 1024 * 1024,
        backlog: int = 128,
    ):
        """Initialize the inbound transport server.

        Args:
            host (str): Interface address to bind.
            port (int): TCP port to bind.
            dispatcher (Dispatcher): Receiver for decoded inbound messages.
            recv_timeout_s (float): Timeout for socket reads.
            accept_timeout_s (float): Timeout for socket accepts.
            max_frame_size (int): Maximum permitted inbound payload size in bytes.
            backlog (int): Maximum number of pending connections.

        Returns:
            None: This initializer configures the inbound transport server.
        """
        # Network binding parameters
        self._host = host
        self._port = port

        # Dispatcher responsible for routing decoded messages
        self._dispatcher = dispatcher

        # Socket timeouts and limits
        self._recv_timeout_s = recv_timeout_s
        self._accept_timeout_s = accept_timeout_s
        self._max_frame_size = max_frame_size
        self._backlog = backlog

        # Shutdown coordination
        self._stop_event = threading.Event()

        # Listening socket and accept thread
        self._server_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None

        # Tracking of active connections and threads
        self._lock = threading.Lock()
        self._connections: set[socket.socket] = set()
        self._conn_threads: set[threading.Thread] = set()

    def start(self) -> None:
        """Bind the listening socket and start the accept loop.

        Returns:
            None

        Raises:
            RuntimeError: If the server has already been started.
            OSError: If socket creation, binding, or listening fails.
        """
        if self._accept_thread is not None:
            raise RuntimeError("Server already started")

        self._stop_event.clear()

        # Create, bind, and configure listening socket
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self._host, self._port))
        server_sock.listen(self._backlog)
        server_sock.settimeout(self._accept_timeout_s)

        self._server_sock = server_sock

        # Start accept loop in a dedicated thread
        t = threading.Thread(
            target=self._accept_loop,
            name="tcp-accept",
            daemon=True,
        )
        self._accept_thread = t
        t.start()

    def stop(self) -> None:
        """Stop the server and close all tracked sockets.

        Returns:
            None
        """
        self._stop_event.set()

        # Close listening socket to unblock accept()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass

        # Snapshot active connections and close them
        with self._lock:
            conns = list(self._connections)

        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

        # Wait for accept thread to terminate
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=5.0)
            self._accept_thread = None

        # Wait for all connection threads to terminate
        with self._lock:
            threads = list(self._conn_threads)

        for t in threads:
            t.join(timeout=5.0)

        # Cleanup internal state
        with self._lock:
            self._connections.clear()
            self._conn_threads.clear()

        self._server_sock = None

    def __enter__(self) -> "TcpServer":
        """Start the server when entering a context manager.

        Returns:
            TcpServer: The started server instance.

        Raises:
            RuntimeError: If the server has already been started.
            OSError: If socket setup fails.
        """
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """Stop the server when leaving a context manager.

        Args:
            exc_type (type[BaseException] | None): Exception type raised inside
            the context, if any.
            exc (BaseException | None): Exception instance raised inside the context, if any.
            tb (TracebackType | None): Traceback associated with ``exc``, if any.

        Returns:
            bool: ``False`` so exceptions propagate to the caller.
        """
        self.stop()
        return False

    def _accept_loop(self) -> None:
        """Accept inbound connections and spawn per-connection readers.

        Returns:
            None
        """
        assert self._server_sock is not None

        while not self._stop_event.is_set():
            try:
                conn, _addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                # Socket closed during shutdown
                break

            # Configure per-connection timeout
            conn.settimeout(self._recv_timeout_s)

            with self._lock:
                self._connections.add(conn)

            # Start per-connection receive loop
            t = threading.Thread(
                target=self._connection_loop,
                args=(conn,),
                name="tcp-conn",
                daemon=True,
            )
            with self._lock:
                self._conn_threads.add(t)
            t.start()

    def _connection_loop(self, conn: socket.socket) -> None:
        """Receive, decode, and dispatch messages from one connection.

        Args:
            conn (socket.socket): Accepted socket connected to a remote peer.

        Returns:
            None
        """
        try:
            while not self._stop_event.is_set():
                frame = self._read_frame(conn)
                if frame is None:
                    # Connection closed or framing error
                    break

                try:
                    msg = self._decode_message(frame)
                except Exception:
                    # Malformed message: ignore and continue
                    continue

                try:
                    self._dispatcher.dispatch(msg)
                except Exception:
                    # Handler errors are not the server's concern
                    continue
        finally:
            # Remove connection from tracking and close socket
            with self._lock:
                self._connections.discard(conn)

            try:
                conn.close()
            except OSError:
                pass

            current = threading.current_thread()
            with self._lock:
                self._conn_threads.discard(current)

    def _read_frame(self, conn: socket.socket) -> Optional[bytes]:
        """Read one length-prefixed payload from a socket.

        The framing contract is a 4-byte big-endian unsigned length followed by
        that many payload bytes. Frames larger than ``_max_frame_size`` are
        treated as protocol violations and terminate the connection.

        Args:
            conn (socket.socket): Accepted socket connected to a remote peer.

        Returns:
            Optional[bytes]: Payload bytes, ``b""`` for an empty frame, or
            ``None`` if the connection closes or violates framing rules.
        """
        header = self._recv_exact(conn, 4)
        if header is None:
            return None

        length = struct.unpack(">I", header)[0]
        if length == 0:
            return b""

        if length > self._max_frame_size:
            # Frame too large: protocol violation
            return None

        payload = self._recv_exact(conn, length)
        return payload

    def _recv_exact(self, conn: socket.socket, n: int) -> Optional[bytes]:
        """Receive exactly ``n`` bytes from a connection.

        Args:
            conn (socket.socket): Accepted socket connected to a remote peer.
            n (int): Number of bytes required.

        Returns:
            Optional[bytes]: Exactly ``n`` bytes, or ``None`` if the stream
            closes, resets, or shutdown interrupts the read.
        """
        chunks: list[bytes] = []
        received = 0

        while received < n and not self._stop_event.is_set():
            try:
                chunk = conn.recv(n - received)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                return None

            if chunk == b"":
                # Peer closed connection
                return None

            chunks.append(chunk)
            received += len(chunk)

        if received < n:
            return None

        return b"".join(chunks)

    def _decode_message(self, frame: bytes) -> "Message":
        """Decode a frame into the protocol-layer message representation.

        Args:
            frame (bytes): Raw payload bytes extracted from a transport frame.

        Returns:
            Message: Decoded protocol message instance.

        Raises:
            Exception: Propagates decoder errors for malformed payloads.
        """
        from protocol.message import Message
        return Message.decode(frame)
