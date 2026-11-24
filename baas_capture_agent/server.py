import base64
import json
import queue
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from baas_capture_agent import __version__, doctor
from baas_capture_agent.capturelog import CaptureLog
from baas_capture_agent.events import EventHub
from baas_capture_agent.imaging import STANDARD_PPI, Image, assess, to_standard
from baas_capture_agent.origins import OriginStore
from baas_capture_agent.page import render
from baas_capture_agent.png import encode_grayscale
from baas_capture_agent.reader import (
    BadPress,
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    Reader,
    ReaderError,
)

HOST = "127.0.0.1"
RETRY_PAUSE = 0.8
HEARTBEAT = 15.0
ERROR_PAUSE = 1.0
SAY = {"blank": "Place your finger flat on the glass.", "faint": "Too light. Press a little firmer."}


class ReaderBusy(Exception):
    pass


class CaptureAgent:
    def __init__(self, reader: Reader, timeout: float, events: EventHub | None = None, log: CaptureLog | None = None):
        self.reader = reader
        self.timeout = timeout
        self.events = events or EventHub()
        self.log = log or CaptureLog(None)
        self._lock = threading.Lock()
        self._attempt: threading.Event | None = None
        self._site: str | None = None
        self._cancel = threading.Event()

    def status(self) -> dict:
        status = self.reader.status()
        return {
            "connected": status.connected,
            "device": status.device,
            "driver": status.driver,
            "capturing": self._lock.locked(),
            "version": __version__,
        }

    def capture(self, site: str | None = None) -> dict:
        if not self._lock.acquire(blocking=False):
            self.log.add(site, "busy")
            raise ReaderBusy("Reader is busy")
        self._cancel.clear()
        self._site = site
        try:
            return self._capture(site)
        except (CaptureCancelled, CaptureTimeout, ReaderError) as exc:
            kind = {CaptureCancelled: "cancelled", CaptureTimeout: "timeout"}.get(type(exc), "error")
            self.events.publish(kind, detail=str(exc))
            self.log.add(site, kind, detail=str(exc))
            if kind == "error":
                time.sleep(ERROR_PAUSE)
            raise
        finally:
            self._attempt = None
            self._lock.release()

    def _capture(self, site: str | None) -> dict:
        deadline = time.monotonic() + self.timeout
        attempt = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CaptureTimeout("No finger detected")
            attempt += 1
            self.events.publish("waiting", attempt=attempt)
            self._attempt = threading.Event()
            if self._cancel.is_set():
                raise CaptureCancelled("Capture cancelled")
            started = time.monotonic()
            moments: dict[str, float] = {}

            def finger_on(moment: str):
                moments[moment] = time.monotonic()
                self.events.publish("finger_on" if moment == "on" else "captured")

            try:
                raw = self.reader.capture(self._attempt, remaining, on_finger=finger_on)
            except BadPress:
                self.events.publish("press_again", reason="faint", say=SAY["faint"])
                self.log.add(site, "rejected-by-reader", attempt=attempt)
                if self._cancel.wait(RETRY_PAUSE):
                    raise CaptureCancelled("Capture cancelled")
                continue
            got_image = time.monotonic()
            self.events.publish("reading")
            image = to_standard(Image(raw.width, raw.height, raw.pixels), raw.ppi)
            quality = assess(image)
            touch = moments.get("on", got_image)
            taken = moments.get("captured", got_image)
            details = {
                "ink": quality.ink,
                "coverage": quality.coverage,
                "size": f"{image.width}x{image.height}",
                "wait_ms": round((touch - started) * 1000),
                "read_ms": round((taken - touch) * 1000),
                "held_ms": round((got_image - taken) * 1000),
                "check_ms": round((time.monotonic() - got_image) * 1000),
            }
            if quality.ok:
                self.events.publish("done", ink=quality.ink, coverage=quality.coverage)
                self.log.add(site, "ok", attempt=attempt, **details)
                png = encode_grayscale(image.pixels, image.width, image.height)
                return {
                    "image": base64.b64encode(png).decode(),
                    "width": image.width,
                    "height": image.height,
                    "ppi": STANDARD_PPI,
                    "device": raw.device,
                    "quality": {"ink": quality.ink, "coverage": quality.coverage},
                    "attempts": attempt,
                }
            self.events.publish("press_again", reason=quality.problem, say=SAY[quality.problem])
            self.log.add(site, f"rejected-{quality.problem}", attempt=attempt, **details)
            if self._cancel.wait(RETRY_PAUSE):
                raise CaptureCancelled("Capture cancelled")

    def cancel(self, site: str | None = None) -> bool:
        attempt = self._attempt
        if attempt is None or site != self._site:
            return False
        self._cancel.set()
        attempt.set()
        return True


_ERRORS = (
    (NoReaderError, HTTPStatus.SERVICE_UNAVAILABLE),
    (ReaderBusy, HTTPStatus.CONFLICT),
    (CaptureCancelled, HTTPStatus.CONFLICT),
    (CaptureTimeout, HTTPStatus.REQUEST_TIMEOUT),
    (ReaderError, HTTPStatus.INTERNAL_SERVER_ERROR),
)


def make_handler(agent: CaptureAgent, origins: OriginStore, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"baas-capture-agent/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        @property
        def origin(self) -> str | None:
            return self.headers.get("Origin")

        def _send(self, status: HTTPStatus, body: bytes, content_type: str):
            self.send_response(status)
            if self.origin and origins.known(self.origin):
                self.send_header("Access-Control-Allow-Origin", self.origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                print(f"{self.path}: client left before the {status.value} reply was sent", flush=True)

        def _json(self, status: HTTPStatus, body: dict | list):
            self._send(status, json.dumps(body).encode(), "application/json")

        def _allowed(self) -> bool:
            if self.origin is None or origins.allow(self.origin):
                return True
            self._json(HTTPStatus.FORBIDDEN, {"detail": "This site is not allowed to use the fingerprint reader"})
            return False

        def _owner(self) -> bool:
            if self.headers.get("X-Agent-Token") == token and (self.origin is None or origins.known(self.origin)):
                return True
            self._json(HTTPStatus.FORBIDDEN, {"detail": "Only the agent's own page can change this"})
            return False

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return {}

        def do_OPTIONS(self):
            if not self.origin or not origins.allow(self.origin):
                self.send_response(HTTPStatus.FORBIDDEN)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", self.origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Agent-Token")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self._send(HTTPStatus.OK, render(token, __version__).encode(), "text/html; charset=utf-8")
                return
            if not self._allowed():
                return
            if path == "/status":
                self._json(HTTPStatus.OK, agent.status())
            elif path == "/doctor":
                status = agent.status()
                self._json(HTTPStatus.OK, doctor.run(status["connected"], status["driver"]))
            elif path == "/log":
                self._json(HTTPStatus.OK, agent.log.recent())
            elif path == "/sites":
                self._json(HTTPStatus.OK, origins.snapshot())
            elif path == "/events":
                self._stream()
            else:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

        def _stream(self):
            listener = agent.events.subscribe()
            self.send_response(HTTPStatus.OK)
            if self.origin:
                self.send_header("Access-Control-Allow-Origin", self.origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(b"retry: 2000\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = listener.get(timeout=HEARTBEAT)
                        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                agent.events.unsubscribe(listener)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path in ("/sites/approve", "/sites/forget"):
                if not self._owner():
                    return
                site = self._body().get("site") or parse_qs(urlsplit(self.path).query).get("site", [""])[0]
                if not site:
                    self._json(HTTPStatus.BAD_REQUEST, {"detail": "Which site?"})
                    return
                (origins.approve if path.endswith("approve") else origins.forget)(site)
                self._json(HTTPStatus.OK, origins.snapshot())
                return
            if not self._allowed():
                return
            if path == "/capture":
                try:
                    capture = agent.capture(self.origin)
                except Exception as exc:
                    for kind, status in _ERRORS:
                        if isinstance(exc, kind):
                            self._json(status, {"detail": str(exc)})
                            return
                    raise
                self._json(HTTPStatus.OK, capture)
            elif path == "/cancel":
                self._json(HTTPStatus.OK, {"cancelled": agent.cancel(self.origin)})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    return Handler


def make_server(agent: CaptureAgent, port: int, origins: OriginStore, token: str | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((HOST, port), make_handler(agent, origins, token or secrets.token_urlsafe(24)))
    server.daemon_threads = True
    return server
