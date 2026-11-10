import base64
import http.client
import json
import struct
import threading
import time
import unittest
import zlib

from baas_capture_agent.__main__ import parse_origins
from baas_capture_agent.png import encode_grayscale
from baas_capture_agent.reader import (
    Capture,
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    ReaderStatus,
)
from baas_capture_agent.server import CaptureAgent, make_server, origin_allowed

KIOSK = "https://baas-app-kappa.vercel.app"
WIDTH, HEIGHT = 4, 3
PIXELS = bytes(range(WIDTH * HEIGHT))


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, width, height, idat = 8, 0, 0, b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
            assert (depth, colour) == (8, 0)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    rows = [raw[y * (width + 1) + 1 : (y + 1) * (width + 1)] for y in range(height)]
    return width, height, b"".join(rows)


class FakeReader:
    def __init__(self, connected=True, finger_after=0.0, error=None):
        self.connected = connected
        self.finger_after = finger_after
        self.error = error
        self.started = threading.Event()

    def status(self):
        if not self.connected:
            return ReaderStatus(connected=False)
        return ReaderStatus(connected=True, device="Digital Persona U.are.U 4000/4000B/4500", driver="uru4000")

    def capture(self, stop, timeout):
        if not self.connected:
            raise NoReaderError("Fingerprint reader not connected")
        self.started.set()
        if self.error:
            raise self.error
        if self.finger_after > timeout:
            if stop.wait(timeout):
                raise CaptureCancelled("Capture cancelled")
            raise CaptureTimeout("No finger detected")
        if stop.wait(self.finger_after):
            raise CaptureCancelled("Capture cancelled")
        return Capture(WIDTH, HEIGHT, PIXELS, "Digital Persona U.are.U 4000/4000B/4500")


class PngTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(decode_png(encode_grayscale(PIXELS, WIDTH, HEIGHT)), (WIDTH, HEIGHT, PIXELS))

    def test_wrong_pixel_count_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_grayscale(PIXELS[:-1], WIDTH, HEIGHT)

    def test_empty_image_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_grayscale(b"", 0, 0)


class OriginTest(unittest.TestCase):
    def test_configured_kiosk_is_allowed(self):
        self.assertTrue(origin_allowed(KIOSK, (KIOSK,)))

    def test_local_development_on_any_port_is_allowed(self):
        for origin in ("http://localhost:8080", "http://127.0.0.1:54321", "http://localhost"):
            self.assertTrue(origin_allowed(origin, (KIOSK,)), origin)

    def test_other_sites_are_refused(self):
        for origin in (None, "", "https://evil.example", "https://localhost.evil.example", "https://localhost:8080"):
            self.assertFalse(origin_allowed(origin, (KIOSK,)), origin)

    def test_origins_are_parsed_from_config(self):
        self.assertEqual(parse_origins(" https://a.example/, https://b.example ,"), ("https://a.example", "https://b.example"))


class ServerTest(unittest.TestCase):
    def start(self, reader, timeout=2.0):
        agent = CaptureAgent(reader, timeout)
        server = make_server(agent, 0, (KIOSK,))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]
        self.assertEqual(server.server_address[0], "127.0.0.1")
        return agent

    def request(self, method, path, origin=KIOSK, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        all_headers = dict(headers or {})
        if origin:
            all_headers["Origin"] = origin
        conn.request(method, path, headers=all_headers)
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response, json.loads(body) if body else None

    def test_status_reports_the_reader(self):
        self.start(FakeReader())

        response, body = self.request("GET", "/status")

        self.assertEqual(response.status, 200)
        self.assertTrue(body["connected"])
        self.assertEqual(body["driver"], "uru4000")
        self.assertFalse(body["capturing"])
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), KIOSK)

    def test_status_without_reader(self):
        self.start(FakeReader(connected=False))

        _, body = self.request("GET", "/status")

        self.assertFalse(body["connected"])
        self.assertIsNone(body["device"])

    def test_capture_returns_a_png(self):
        self.start(FakeReader())

        response, body = self.request("POST", "/capture")

        self.assertEqual(response.status, 200)
        self.assertEqual((body["width"], body["height"]), (WIDTH, HEIGHT))
        self.assertEqual(decode_png(base64.b64decode(body["image"])), (WIDTH, HEIGHT, PIXELS))

    def test_capture_without_reader_is_503(self):
        self.start(FakeReader(connected=False))

        response, body = self.request("POST", "/capture")

        self.assertEqual(response.status, 503)
        self.assertEqual(body["detail"], "Fingerprint reader not connected")

    def test_no_finger_times_out(self):
        self.start(FakeReader(finger_after=60), timeout=0.2)

        response, body = self.request("POST", "/capture")

        self.assertEqual(response.status, 408)
        self.assertEqual(body["detail"], "No finger detected")

    def test_capture_can_be_cancelled(self):
        reader = FakeReader(finger_after=60)
        self.start(reader, timeout=30)
        result = {}

        def capture():
            result["response"], result["body"] = self.request("POST", "/capture")

        worker = threading.Thread(target=capture)
        worker.start()
        self.assertTrue(reader.started.wait(5))
        _, cancel = self.request("POST", "/cancel")
        worker.join(5)

        self.assertTrue(cancel["cancelled"])
        self.assertEqual(result["response"].status, 409)
        self.assertEqual(result["body"]["detail"], "Capture cancelled")

    def test_second_capture_while_busy_is_refused(self):
        reader = FakeReader(finger_after=0.5)
        self.start(reader)
        threading.Thread(target=lambda: self.request("POST", "/capture")).start()
        self.assertTrue(reader.started.wait(5))

        response, body = self.request("POST", "/capture")
        _, status = self.request("GET", "/status")

        self.assertEqual(response.status, 409)
        self.assertEqual(body["detail"], "Reader is busy")
        self.assertTrue(status["capturing"])
        time.sleep(0.6)

    def test_cancel_with_nothing_running(self):
        self.start(FakeReader())

        _, body = self.request("POST", "/cancel")

        self.assertFalse(body["cancelled"])

    def test_foreign_site_is_refused(self):
        self.start(FakeReader())

        response, _ = self.request("POST", "/capture", origin="https://evil.example")

        self.assertEqual(response.status, 403)
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))

    def test_preflight_allows_the_kiosk_and_private_network_access(self):
        self.start(FakeReader())

        response, _ = self.request(
            "OPTIONS",
            "/capture",
            headers={
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Private-Network": "true",
            },
        )

        self.assertEqual(response.status, 204)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), KIOSK)
        self.assertEqual(response.getheader("Access-Control-Allow-Private-Network"), "true")

    def test_preflight_from_a_foreign_site_is_refused(self):
        self.start(FakeReader())

        response, _ = self.request("OPTIONS", "/capture", origin="https://evil.example")

        self.assertEqual(response.status, 403)

    def test_unknown_path_is_404(self):
        self.start(FakeReader())

        response, _ = self.request("GET", "/nope")

        self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
