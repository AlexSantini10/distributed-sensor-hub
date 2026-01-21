import socket
import struct
import threading
from typing import Optional, Protocol


class Dispatcher(Protocol):
    """
    Protocol interface for a message dispatcher.
    """
    def dispatch(self, msg) -> None:
        ...


class TcpServer:
    """
    Multi-threaded TCP server using a length-prefixed framing protocol.

    Responsibilities:
    - Accept incoming TCP connections.
    - Spawn one thread per connection.
    - Read framed messages from each connection.
    - Decode messages and hand them off to the dispatcher.
    - Track active connections for graceful shutdown.

    The server does NOT interpret message semantics.
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
        """
        Start the TCP server.

        Creates the listening socket and launches the accept loop
        in a dedicated daemon thread.
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
        """
        Gracefully stop the server.

        Signals all threads to stop, closes the listening socket,
        shuts down all active connections, and joins all threads.
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

    def __enter__(self):
        """Context manager entry: start server."""
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Context manager exit: stop server."""
        self.stop()
        return False

    def _accept_loop(self) -> None:
        """
        Accept loop running in a dedicated thread.

        Accepts incoming connections and spawns one thread per
        connection to handle message reception.
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
        """
        Per-connection receive loop.

        Reads framed messages from the socket, decodes them,
        and forwards them to the dispatcher.
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
        """
        Read a single length-prefixed frame from the socket.

        Frame format:
        - 4-byte unsigned integer (big-endian) indicating payload length
        - payload bytes

        Returns:
            The payload bytes, or None if the connection is closed or invalid.
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
        """
        Receive exactly n bytes from the socket.

        Handles partial reads and timeouts.
        Returns None if the connection is closed or interrupted.
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

    def _decode_message(self, frame: bytes):
        """
        Decode a raw frame into a Message instance.

        This method isolates protocol decoding from the networking logic.
        """
        from protocol.message import Message
        return Message.decode(frame)
