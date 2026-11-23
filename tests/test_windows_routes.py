import ctypes
import threading
import unittest

from baas_capture_agent.dpfpdd import (
    E_DEVICE_BUSY,
    QUALITY_CANCELED,
    QUALITY_TIMED_OUT,
    CaptureParam,
    CaptureResult,
    DevInfo,
    ImageInfo,
    capture_from,
    error_text,
)
from baas_capture_agent.reader import (
    BadPress,
    CaptureCancelled,
    CaptureTimeout,
    FirstConnected,
    NoReaderError,
    ReaderError,
    ReaderStatus,
)


class Route:
    def __init__(self, name, connected):
        self.name, self.connected, self.used = name, connected, False

    def status(self):
        return ReaderStatus(connected=self.connected, device=self.name, driver=self.name)

    def capture(self, stop, timeout, on_finger=None):
        self.used = True
        return self.name


class FirstConnectedTest(unittest.TestCase):
    def test_uses_windows_framework_when_it_sees_the_reader(self):
        wbf, sdk = Route("winbio", True), Route("dpfpdd", True)
        reader = FirstConnected([wbf, sdk])
        self.assertEqual(reader.status().driver, "winbio")
        self.assertEqual(reader.capture(threading.Event(), 1), "winbio")
        self.assertFalse(sdk.used)

    def test_falls_back_to_the_sdk_when_the_old_driver_owns_the_reader(self):
        reader = FirstConnected([Route("winbio", False), Route("dpfpdd", True)])
        self.assertEqual(reader.status().driver, "dpfpdd")
        self.assertEqual(reader.capture(threading.Event(), 1), "dpfpdd")

    def test_no_route_sees_a_reader(self):
        reader = FirstConnected([Route("winbio", False), Route("dpfpdd", False)])
        self.assertFalse(reader.status().connected)
        with self.assertRaises(NoReaderError):
            reader.capture(threading.Event(), 1)


def result(success=1, quality=0, width=4, height=3, res=500, bpp=8):
    r = CaptureResult(size=ctypes.sizeof(CaptureResult), success=success, quality=quality)
    r.info = ImageInfo(ctypes.sizeof(ImageInfo), width, height, res, bpp)
    return r


class DpfpddTest(unittest.TestCase):
    def test_structures_match_the_sdk_header(self):
        self.assertEqual(ctypes.sizeof(DevInfo), 1452)
        self.assertEqual(DevInfo.vendor_id.offset, 1412)
        self.assertEqual(DevInfo.modality.offset, 1444)
        self.assertEqual(ctypes.sizeof(CaptureParam), 16)
        self.assertEqual(ctypes.sizeof(CaptureResult), 36)

    def test_a_good_capture_becomes_an_image(self):
        capture = capture_from(result(), bytes(range(12)) + b"spare", "4500")
        self.assertEqual((capture.width, capture.height, capture.pixels, capture.ppi), (4, 3, bytes(range(12)), 500.0))

    def test_cancel_and_timeout_are_reported(self):
        with self.assertRaises(CaptureCancelled):
            capture_from(result(success=0, quality=QUALITY_CANCELED), b"", "4500")
        with self.assertRaises(CaptureTimeout):
            capture_from(result(success=0, quality=QUALITY_TIMED_OUT), b"", "4500")

    def test_an_unreadable_press_asks_for_another(self):
        with self.assertRaises(BadPress):
            capture_from(result(success=0, quality=1 << 8), b"", "4500")

    def test_odd_images_are_refused(self):
        with self.assertRaises(ReaderError):
            capture_from(result(bpp=16), bytes(24), "4500")
        with self.assertRaises(ReaderError):
            capture_from(result(), bytes(5), "4500")

    def test_errors_in_words(self):
        self.assertIn("Another program", error_text(E_DEVICE_BUSY))
        self.assertEqual(error_text(0x05BA000B), "DigitalPersona reader error 0x05BA000B")


if __name__ == "__main__":
    unittest.main()
