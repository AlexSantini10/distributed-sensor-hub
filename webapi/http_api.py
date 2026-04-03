"""Serve HTTP snapshots of replicated node state and incremental updates.

Responsibilities:
    - Expose full state and update buffers through polling endpoints.
    - Preserve the snapshot schema produced by the state worker.
    - Provide CORS-enabled read-only endpoints for external dashboards and tests.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from protocol.contracts import HttpContentType, TextEncoding


class RequestHandler(BaseHTTPRequestHandler):
    """Handle read-only HTTP requests for state and update snapshots.

    Attributes:
        _state_provider (Any): Zero-argument callable returning the current full state snapshot.
        _updates_provider (Any): Zero-argument callable returning the current incremental updates snapshot.
        _log (Any): Logger-like object used for request handling failures.
    """

    def __init__(
        self,
        *args: Any,
        state_provider: Any = None,
        updates_provider: Any = None,
        log: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the request handler with snapshot providers.

        Args:
            *args (Any): Positional arguments required by ``BaseHTTPRequestHandler``.
            state_provider (Any): Callable returning the full state snapshot.
            updates_provider (Any): Callable returning the incremental updates snapshot.
            log (Any): Logger-like object used for request failure reporting.
            **kwargs (Any): Keyword arguments required by ``BaseHTTPRequestHandler``.

        Returns:
            None: This constructor does not return a value.
        """
        self._state_provider = state_provider
        self._updates_provider = updates_provider
        self._log = log
        super().__init__(*args, **kwargs)

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

            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()

        except Exception:
            if self._log:
                self._log.error(
                    "Unhandled exception in HTTP handler",
                    exc_info=True,
                )
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
            if self._log:
                self._log.error(
                    "Failed to produce state snapshot",
                    exc_info=True,
                )
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
            if self._log:
                self._log.error(
                    "Failed to produce updates snapshot",
                    exc_info=True,
                )
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

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress the standard library's default per-request stderr logging.

        Args:
            format (str): Standard-library log format string.
            *args (Any): Format arguments supplied by the HTTP server.

        Returns:
            None: This method intentionally emits no output.
        """
        return


class WebAPIServer(threading.Thread):
    """Host the threaded HTTP API that exposes node-state snapshots.

    Attributes:
        _log (Any): Logger-like object used for lifecycle and failure reporting.
        _server (ThreadingHTTPServer): Threaded HTTP server serving snapshot requests.
    """

    def __init__(
        self,
        host: str,
        port: int,
        state_provider: Any,
        updates_provider: Any,
        log: Any,
    ) -> None:
        """Initialize the threaded HTTP server wrapper.

        Args:
            host (str): Interface address for the HTTP bind.
            port (int): TCP port for the HTTP bind.
            state_provider (Any): Callable returning the full state snapshot.
            updates_provider (Any): Callable returning the incremental updates snapshot.
            log (Any): Logger-like object used for lifecycle reporting.

        Returns:
            None: This constructor does not return a value.

        Raises:
            Exception: Propagates bind failures from ``ThreadingHTTPServer`` construction.
        """
        super().__init__(daemon=True)
        self._log = log

        def handler_factory(*args: Any, **kwargs: Any) -> RequestHandler:
            """Bind snapshot providers into per-request handler instances.

            Args:
                *args (Any): Positional arguments supplied by the HTTP server.
                **kwargs (Any): Keyword arguments supplied by the HTTP server.

            Returns:
                RequestHandler: Configured request handler instance.
            """
            return RequestHandler(
                *args,
                state_provider=state_provider,
                updates_provider=updates_provider,
                log=log,
                **kwargs,
            )

        try:
            self._server = ThreadingHTTPServer(
                (host, port),
                handler_factory,
            )
        except Exception:
            if log:
                log.critical(
                    f"Failed to bind WebAPI on {host}:{port}",
                    exc_info=True,
                )
            raise

    def run(self) -> None:
        """Serve HTTP requests until the server is shut down.

        Returns:
            None: This method serves requests until termination.

        Raises:
            Exception: Propagates unrecoverable server failures after logging them.
        """
        try:
            self._log.info("WebAPI thread started")
            self._server.serve_forever()
        except Exception:
            if self._log:
                self._log.critical(
                    "WebAPI thread crashed",
                    exc_info=True,
                )
            raise

    def stop(self) -> None:
        """Stop the HTTP server and release the serving loop.

        Returns:
            None: This method signals the server to stop in place.
        """
        try:
            self._server.shutdown()
            self._log.info("WebAPI server stopped")
        except Exception:
            if self._log:
                self._log.error(
                    "Error while stopping WebAPI",
                    exc_info=True,
                )
