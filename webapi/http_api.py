"""Serve HTTP snapshots of replicated node state and incremental updates.

Responsibilities:
    - Expose full state and update buffers through polling endpoints.
    - Preserve the snapshot schema produced by the state worker.
    - Provide CORS-enabled read-only endpoints for external dashboards and tests.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from protocol.contracts import HttpContentType, TextEncoding
from utils.typing import LoggerLike, SnapshotProvider


class RequestHandler(BaseHTTPRequestHandler):
    """Handle read-only HTTP requests for state and update snapshots.

    Attributes:
        _state_provider (SnapshotProvider): Zero-argument callable returning the current full state snapshot.
        _updates_provider (SnapshotProvider): Zero-argument callable returning the current incremental updates snapshot.
        _log (LoggerLike | None): Logger-like object used for request handling failures.
    """

    _state_provider: SnapshotProvider
    _updates_provider: SnapshotProvider
    _membership_provider: SnapshotProvider | None
    _log: LoggerLike | None

    def _send_cors_headers(self) -> None:
        """Write the permissive CORS headers required by browser polling clients.

        Returns:
            None: This method mutates the current HTTP response only.
        """
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        """Respond to CORS preflight requests for read-only endpoints.

        Returns:
            None: This method writes the HTTP response directly.
        """
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests to snapshot endpoints.

        Returns:
            None: This method writes the HTTP response directly.
        """
        try:
            if self.path == "/api/state":
                self._handle_state()
            elif self.path == "/api/updates":
                self._handle_updates()
            elif self.path == "/api/membership":
                self._handle_membership()
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()
        except Exception:
            if self._log is not None:
                self._log.error("Unhandled exception in HTTP handler", exc_info=True)
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()

    def _handle_state(self) -> None:
        """Serialize and return the current full-state snapshot.

        Returns:
            None: This method writes the HTTP response directly.
        """
        try:
            state = self._state_provider()
            payload = json.dumps(state).encode(TextEncoding.UTF8.value)
        except Exception:
            if self._log is not None:
                self._log.error("Failed to produce state snapshot", exc_info=True)
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()
            return

        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", HttpContentType.JSON.value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_updates(self) -> None:
        """Serialize and return the current incremental-update snapshot.

        Returns:
            None: This method writes the HTTP response directly.
        """
        try:
            updates = self._updates_provider()
            payload = json.dumps(updates).encode(TextEncoding.UTF8.value)
        except Exception:
            if self._log is not None:
                self._log.error("Failed to produce updates snapshot", exc_info=True)
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()
            return

        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", HttpContentType.JSON.value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_membership(self) -> None:
        """Serialize and return the current Phi-based membership snapshot."""
        if self._membership_provider is None:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
            return

        try:
            membership = self._membership_provider()
            payload = json.dumps(membership).encode(TextEncoding.UTF8.value)
        except Exception:
            if self._log is not None:
                self._log.error("Failed to produce membership snapshot", exc_info=True)
            self.send_response(500)
            self._send_cors_headers()
            self.end_headers()
            return

        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", HttpContentType.JSON.value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the standard library's default per-request stderr logging.

        Args:
            format (str): Standard-library log format string.
            *args (object): Format arguments supplied by the HTTP server.

        Returns:
            None: This method intentionally emits no output.
        """
        return


def build_request_handler(
    state_provider: SnapshotProvider,
    updates_provider: SnapshotProvider,
    membership_provider: SnapshotProvider | None,
    log: LoggerLike | None,
) -> type[RequestHandler]:
    """Create a concrete request-handler class bound to snapshot providers.

    Args:
        state_provider (SnapshotProvider): Callable returning the full state snapshot.
        updates_provider (SnapshotProvider): Callable returning the incremental updates snapshot.
        log (LoggerLike | None): Logger-like object used for request failure reporting.

    Returns:
        type[RequestHandler]: Configured request-handler class for ``ThreadingHTTPServer``.
    """

    class ConfiguredRequestHandler(RequestHandler):
        """Bind snapshot providers into a concrete request-handler class."""

        _state_provider = staticmethod(state_provider)
        _updates_provider = staticmethod(updates_provider)
        _membership_provider = (
            staticmethod(membership_provider)
            if membership_provider is not None
            else None
        )
        _log = log

    return ConfiguredRequestHandler


class WebAPIServer(threading.Thread):
    """Host the threaded HTTP API that exposes node-state snapshots.

    Attributes:
        _log (LoggerLike | None): Logger-like object used for lifecycle and failure reporting.
        _server (ThreadingHTTPServer): Threaded HTTP server serving snapshot requests.
    """

    def __init__(
        self,
        host: str,
        port: int,
        state_provider: SnapshotProvider,
        updates_provider: SnapshotProvider,
        membership_provider: SnapshotProvider | None,
        log: LoggerLike | None,
    ) -> None:
        """Initialize the threaded HTTP server wrapper.

        Args:
            host (str): Interface address for the HTTP bind.
            port (int): TCP port for the HTTP bind.
            state_provider (SnapshotProvider): Callable returning the full state snapshot.
            updates_provider (SnapshotProvider): Callable returning the incremental updates snapshot.
            membership_provider (SnapshotProvider | None): Optional callable returning
                the Phi-based membership snapshot.
            log (LoggerLike | None): Logger-like object used for lifecycle reporting.

        Returns:
            None: This constructor does not return a value.
        """
        super().__init__(daemon=True)
        self._log = log

        handler_cls = build_request_handler(
            state_provider=state_provider,
            updates_provider=updates_provider,
            membership_provider=membership_provider,
            log=log,
        )
        try:
            self._server = ThreadingHTTPServer((host, port), handler_cls)
        except Exception:
            if log is not None:
                log.critical(f"Failed to bind WebAPI on {host}:{port}", exc_info=True)
            raise

    def run(self) -> None:
        """Serve HTTP requests until the server is shut down.

        Returns:
            None: This method serves requests until termination.
        """
        log = self._log
        try:
            if log is not None:
                log.info("WebAPI thread started")
            self._server.serve_forever()
        except Exception:
            if log is not None:
                log.critical("WebAPI thread crashed", exc_info=True)
            raise

    def stop(self) -> None:
        """Stop the HTTP server and release the serving loop.

        Returns:
            None: This method signals the server to stop in place.
        """
        log = self._log
        try:
            self._server.shutdown()
            if log is not None:
                log.info("WebAPI server stopped")
        except Exception:
            if log is not None:
                log.error("Error while stopping WebAPI", exc_info=True)
