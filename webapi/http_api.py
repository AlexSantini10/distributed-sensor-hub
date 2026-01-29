import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class RequestHandler(BaseHTTPRequestHandler):
	def __init__(self, *args, state_provider=None, log=None, **kwargs):
		self._state_provider = state_provider
		self._log = log
		super().__init__(*args, **kwargs)

	def do_GET(self):
		try:
			if self.path == "/api/sensors":
				self._handle_sensors()
			else:
				self.send_response(404)
				self.end_headers()
		except Exception:
			if self._log:
				self._log.error("Unhandled exception in HTTP handler", exc_info=True)
			self.send_response(500)
			self.end_headers()

	def _handle_sensors(self):
		try:
			state = self._state_provider()
			payload = json.dumps(state).encode("utf-8")
		except Exception:
			if self._log:
				self._log.error("Failed to produce sensor state", exc_info=True)
			self.send_response(500)
			self.end_headers()
			return

		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		self.wfile.write(payload)

	def log_message(self, format, *args):
		return  # silence default HTTP logs


class WebAPIServer(threading.Thread):
	def __init__(self, host, port, state_provider, log):
		super().__init__(daemon=True)
		self._log = log

		def handler_factory(*args, **kwargs):
			return RequestHandler(
				*args,
				state_provider=state_provider,
				log=log,
				**kwargs,
			)

		try:
			self._server = ThreadingHTTPServer((host, port), handler_factory)
		except Exception:
			if log:
				log.critical(
					f"Failed to bind WebAPI on {host}:{port}",
					exc_info=True,
				)
			raise

	def run(self):
		try:
			self._log.info("WebAPI thread started")
			self._server.serve_forever()
		except Exception:
			if self._log:
				self._log.critical("WebAPI thread crashed", exc_info=True)
			raise

	def stop(self):
		try:
			self._server.shutdown()
			self._log.info("WebAPI server stopped")
		except Exception:
			if self._log:
				self._log.error("Error while stopping WebAPI", exc_info=True)
