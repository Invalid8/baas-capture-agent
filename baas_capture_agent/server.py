import base64
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from baas_capture_agent import __version__
from baas_capture_agent.png import encode_grayscale
from baas_capture_agent.reader import (
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    Reader,
    ReaderError,
)

HOST = "127.0.0.1"


class ReaderBusy(Exception):
    pass


class CaptureAgent:
    def __init__(self, reader: Reader, timeout: float):
        self.reader = reader
        self.timeout = timeout
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None

    def status(self) -> dict:
        status = self.reader.status()
        return {
            "connected": status.connected,
            "device": status.device,
            "driver": status.driver,
            "capturing": self._lock.locked(),
            "version": __version__,
        }

    def capture(self) -> dict:
        if not self._lock.acquire(blocking=False):
            raise ReaderBusy("Reader is busy")
        try:
            self._stop = threading.Event()
            capture = self.reader.capture(self._stop, self.timeout)
        finally:
            self._stop = None
            self._lock.release()
        png = encode_grayscale(capture.pixels, capture.width, capture.height)
        return {
            "image": base64.b64encode(png).decode(),
            "width": capture.width,
            "height": capture.height,
            "device": capture.device,
        }

    def cancel(self) -> bool:
        stop = self._stop
        if stop is None:
            return False
        stop.set()
        return True


def origin_allowed(origin: str | None, allowed: tuple[str, ...]) -> bool:
    if not origin:
        return False
    if origin in allowed:
        return True
    parts = urlsplit(origin)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")


_ERRORS = (
    (NoReaderError, HTTPStatus.SERVICE_UNAVAILABLE),
    (ReaderBusy, HTTPStatus.CONFLICT),
    (CaptureCancelled, HTTPStatus.CONFLICT),
    (CaptureTimeout, HTTPStatus.REQUEST_TIMEOUT),
    (ReaderError, HTTPStatus.INTERNAL_SERVER_ERROR),
)


def make_handler(agent: CaptureAgent, allowed_origins: tuple[str, ...]):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"baas-capture-agent/{__version__}"

        def log_message(self, fmt, *args):
            pass

        def _cors(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            if not origin_allowed(origin, allowed_origins):
                return False
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            return True

        def _json(self, status: HTTPStatus, body: dict):
            data = json.dumps(body).encode()
            self.send_response(status)
            if not self._cors():
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _refuse_foreign_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None and not origin_allowed(origin, allowed_origins):
                self._json(HTTPStatus.FORBIDDEN, {"detail": "Origin not allowed"})
                return True
            return False

        def do_OPTIONS(self):
            origin = self.headers.get("Origin")
            if not origin_allowed(origin, allowed_origins):
                self.send_response(HTTPStatus.FORBIDDEN)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self._refuse_foreign_origin():
                return
            if self.path == "/status":
                self._json(HTTPStatus.OK, agent.status())
            else:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

        def do_POST(self):
            if self._refuse_foreign_origin():
                return
            if self.path == "/capture":
                try:
                    self._json(HTTPStatus.OK, agent.capture())
                except Exception as exc:
                    for kind, status in _ERRORS:
                        if isinstance(exc, kind):
                            self._json(status, {"detail": str(exc)})
                            return
                    raise
            elif self.path == "/cancel":
                self._json(HTTPStatus.OK, {"cancelled": agent.cancel()})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    return Handler


def make_server(agent: CaptureAgent, port: int, allowed_origins: tuple[str, ...]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((HOST, port), make_handler(agent, allowed_origins))
    server.daemon_threads = True
    return server
