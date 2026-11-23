import base64
import http.client
import json
import struct
import threading
import time
import unittest
import zlib

import tempfile
from pathlib import Path

from baas_capture_agent.capturelog import CaptureLog
from baas_capture_agent.events import EventHub
from baas_capture_agent.imaging import Image
from baas_capture_agent.origins import OriginStore
from baas_capture_agent.png import encode_grayscale
from baas_capture_agent.reader import (
    Capture,
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    ReaderStatus,
)
from baas_capture_agent.server import CaptureAgent, make_server
from tests.test_imaging import ridges

KIOSK = "https://baas-app-kappa.vercel.app"
TOKEN = "page-token"
PRINT: Image = ridges(64, 64)
BLANK = Image(64, 64, bytes([235] * 64 * 64))
WIDTH, HEIGHT, PIXELS = PRINT.width, PRINT.height, PRINT.pixels


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
    def __init__(self, connected=True, finger_after=0.0, error=None, images=(PRINT,), ppi=None):
        self.connected = connected
        self.finger_after = finger_after
        self.error = error
        self.images = list(images)
        self.ppi = ppi
        self.started = threading.Event()

    def status(self):
        if not self.connected:
            return ReaderStatus(connected=False)
        return ReaderStatus(connected=True, device="Digital Persona U.are.U 4000/4000B/4500", driver="uru4000")

    def capture(self, stop, timeout, on_finger=None):
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
        if on_finger:
            on_finger("on")
            on_finger("captured")
        image = self.images.pop(0) if len(self.images) > 1 else self.images[0]
        return Capture(image.width, image.height, image.pixels, "Digital Persona U.are.U 4000/4000B/4500", self.ppi)


class PngTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(decode_png(encode_grayscale(PIXELS, WIDTH, HEIGHT)), (WIDTH, HEIGHT, PIXELS))

    def test_wrong_pixel_count_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_grayscale(PIXELS[:-1], WIDTH, HEIGHT)

    def test_empty_image_is_rejected(self):
        with self.assertRaises(ValueError):
            encode_grayscale(b"", 0, 0)


class ServerTest(unittest.TestCase):
    def start(self, reader, timeout=2.0, prompt=None):
        folder = Path(tempfile.mkdtemp())
        self.events = EventHub()
        agent = CaptureAgent(reader, timeout, self.events, CaptureLog(folder / "capture.log"))
        self.origins = OriginStore(folder / "sites.json", (), prompt)
        server = make_server(agent, 0, self.origins, TOKEN)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]
        self.assertEqual(server.server_address[0], "127.0.0.1")
        return agent

    def request(self, method, path, origin=KIOSK, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        all_headers = dict(headers or {})
        if origin:
            all_headers["Origin"] = origin
        data = json.dumps(body).encode() if body is not None else None
        if data:
            all_headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=all_headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        kind = response.getheader("Content-Type") or ""
        return response, json.loads(raw) if raw and "json" in kind else raw

    def test_status_reports_the_reader(self):
        self.start(FakeReader())

        response, body = self.request("GET", "/status")

        self.assertEqual(response.status, 200)
        self.assertTrue(body["connected"])
        self.assertEqual(body["driver"], "uru4000")
        self.assertFalse(body["capturing"])
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), KIOSK)

    def test_a_pc_without_fingerprint_support_still_runs_the_agent(self):
        from baas_capture_agent.reader import UnavailableReader

        self.start(UnavailableReader("Windows fingerprint support is missing: install the U.are.U WBF driver"))

        _, status = self.request("GET", "/status")
        response, body = self.request("POST", "/capture")

        self.assertFalse(status["connected"])
        self.assertEqual(response.status, 503)
        self.assertIn("WBF driver", body["detail"])

    def test_status_without_reader(self):
        self.start(FakeReader(connected=False))

        _, body = self.request("GET", "/status")

        self.assertFalse(body["connected"])
        self.assertIsNone(body["device"])

    def test_capture_returns_a_png(self):
        self.start(FakeReader())

        response, body = self.request("POST", "/capture")

        self.assertEqual(response.status, 200)
        self.assertEqual((body["width"], body["height"], body["ppi"], body["attempts"]), (WIDTH, HEIGHT, 500.0, 1))
        self.assertEqual(decode_png(base64.b64decode(body["image"])), (WIDTH, HEIGHT, PIXELS))
        self.assertGreater(body["quality"]["coverage"], 0.5)

    def test_capture_is_scaled_to_500_ppi(self):
        self.start(FakeReader(images=(ridges(128, 128),), ppi=512.0))

        _, body = self.request("POST", "/capture")

        self.assertEqual((body["width"], body["height"]), (125, 125))

    def test_a_blank_press_is_asked_again_inside_the_same_capture(self):
        self.start(FakeReader(images=(BLANK, PRINT)), timeout=5)
        listener = self.events.subscribe()

        response, body = self.request("POST", "/capture")

        self.assertEqual((response.status, body["attempts"]), (200, 2))
        kinds = []
        while not listener.empty():
            kinds.append(listener.get_nowait())
        self.assertEqual(
            [e["event"] for e in kinds],
            ["waiting", "finger_on", "captured", "reading", "press_again", "waiting", "finger_on", "captured", "reading", "done"],
        )
        self.assertEqual(kinds[4]["reason"], "blank")
        _, log = self.request("GET", "/log")
        self.assertEqual([e["result"] for e in log], ["ok", "rejected-blank"])
        self.assertEqual(log[0]["site"], KIOSK)

    def test_only_blank_presses_end_in_a_timeout(self):
        self.start(FakeReader(images=(BLANK,)), timeout=1.2)

        response, body = self.request("POST", "/capture")

        self.assertEqual((response.status, body["detail"]), (408, "No finger detected"))

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

    def test_a_new_site_is_refused_when_the_person_says_no(self):
        asked = []
        self.start(FakeReader(), prompt=lambda origin: asked.append(origin) or False)

        response, _ = self.request("POST", "/capture", origin="https://evil.example")
        again, _ = self.request("POST", "/capture", origin="https://evil.example")

        self.assertEqual((response.status, again.status), (403, 403))
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        self.assertEqual(asked, ["https://evil.example"])

    def test_a_new_site_is_asked_once_then_remembered(self):
        asked = []
        self.start(FakeReader(), prompt=lambda origin: asked.append(origin) or True)

        first, _ = self.request("GET", "/status", origin="https://clinic.example")
        second, _ = self.request("GET", "/status", origin="https://clinic.example")

        self.assertEqual((first.status, second.status), (200, 200))
        self.assertEqual(first.getheader("Access-Control-Allow-Origin"), "https://clinic.example")
        self.assertEqual(asked, ["https://clinic.example"])
        self.assertIn("https://clinic.example", self.origins.snapshot()["approved"])

    def test_without_a_prompt_window_the_site_waits_for_the_page(self):
        self.start(FakeReader(), prompt=lambda origin: None)

        refused, _ = self.request("GET", "/status", origin="https://clinic.example")
        _, sites = self.request("GET", "/sites", origin=None)
        _, after = self.request(
            "POST", "/sites/approve", origin=None, headers={"X-Agent-Token": TOKEN}, body={"site": "https://clinic.example"}
        )
        allowed, _ = self.request("GET", "/status", origin="https://clinic.example")

        self.assertEqual((refused.status, allowed.status), (403, 200))
        self.assertEqual(sites["waiting"], ["https://clinic.example"])
        self.assertEqual((after["waiting"], after["approved"]), ([], ["https://clinic.example"]))

    def test_sites_can_only_be_changed_with_the_page_token(self):
        self.start(FakeReader())

        for headers in ({}, {"X-Agent-Token": "guess"}):
            response, _ = self.request("POST", "/sites/approve", headers=headers, body={"site": "https://evil.example"})
            self.assertEqual(response.status, 403)
        response, _ = self.request(
            "POST", "/sites/approve", origin="https://evil.example", headers={"X-Agent-Token": TOKEN},
            body={"site": "https://evil.example"},
        )
        self.assertEqual(response.status, 403)
        self.assertEqual(self.origins.snapshot()["approved"], [])

    def test_the_self_check_page_is_served_with_its_token(self):
        self.start(FakeReader())

        response, html = self.request("GET", "/", origin=None)

        self.assertEqual(response.status, 200)
        self.assertIn(b"Test the reader", html)
        self.assertIn(TOKEN.encode(), html)

    def test_events_stream_to_an_allowed_site(self):
        self.start(FakeReader())
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/events", headers={"Origin": KIOSK})
        response = conn.getresponse()
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), KIOSK)
        response.fp.readline()
        response.fp.readline()
        time.sleep(0.1)
        self.events.publish("waiting", attempt=1)
        line = response.fp.readline().decode()
        conn.close()
        self.assertEqual(json.loads(line.removeprefix("data: ")), {"event": "waiting", "attempt": 1})

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
        self.assertIn("X-Agent-Token", response.getheader("Access-Control-Allow-Headers"))
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
