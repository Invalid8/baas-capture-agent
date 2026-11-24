import ctypes
import threading
import time
import unittest

from baas_capture_agent.dpfpdd import QUALITY_CANCELED, DpfpddReader, DevInfo
from baas_capture_agent.reader import CaptureCancelled, CaptureTimeout, Watch
from baas_capture_agent.winbio import WINBIO_E_CANCELED, WinBioReader
from tests.test_winbio import HEIGHT, PIXELS, WIDTH, sample


class WatchTest(unittest.TestCase):
    def watch(self, stop, timeout):
        cancelled = threading.Event()
        return Watch(stop, timeout, cancelled.set), cancelled

    def test_the_callers_stop_cancels(self):
        stop = threading.Event()
        watch, cancelled = self.watch(stop, 30)
        stop.set()
        self.assertTrue(cancelled.wait(1))
        self.assertEqual(watch.reason, "cancelled")

    def test_the_timeout_cancels(self):
        watch, cancelled = self.watch(threading.Event(), 0.1)
        self.assertTrue(cancelled.wait(1))
        self.assertEqual(watch.reason, "timeout")

    def test_no_timeout_waits_for_stop_only(self):
        watch, cancelled = self.watch(threading.Event(), None)
        self.assertFalse(cancelled.wait(0.3))
        watch.done()

    def test_after_done_nothing_is_cancelled_and_stop_is_left_alone(self):
        stop = threading.Event()
        watch, cancelled = self.watch(stop, 0.2)
        watch.done()
        time.sleep(0.4)
        stop.set()
        self.assertFalse(cancelled.wait(0.3))
        self.assertIsNone(watch.reason)

    def test_done_never_sets_the_callers_stop(self):
        stop = threading.Event()
        watch, _ = self.watch(stop, 30)
        watch.done()
        self.assertFalse(stop.is_set())


class FakeDpfpdd:
    def __init__(self, finger: bool):
        self.finger = finger
        self.cancelled = threading.Event()
        self.closed = False

    def dpfpdd_open(self, name, device):
        return 0

    def dpfpdd_capture(self, device, param, timeout, result, size, image):
        out = result._obj
        if not self.finger:
            self.cancelled.wait(5)
            out.quality = QUALITY_CANCELED
            return 0
        out.success, out.quality = 1, 0
        out.info.width, out.info.height, out.info.res, out.info.bpp = WIDTH, HEIGHT, 500, 8
        size._obj.value = len(PIXELS)
        ctypes.memmove(image, PIXELS, len(PIXELS))
        return 0

    def dpfpdd_cancel(self, device):
        self.cancelled.set()
        return 0

    def dpfpdd_close(self, device):
        self.closed = True
        return 0


def dpfpdd_reader(dll):
    reader = object.__new__(DpfpddReader)
    reader._dll = dll
    reader._readers = lambda: [DevInfo()]
    return reader


class DpfpddCaptureTest(unittest.TestCase):
    def test_a_press_becomes_an_image_and_the_stop_is_left_alone(self):
        dll = FakeDpfpdd(finger=True)
        stop = threading.Event()
        capture = dpfpdd_reader(dll).capture(stop, 5)
        self.assertEqual((capture.width, capture.height, capture.pixels, capture.ppi), (WIDTH, HEIGHT, PIXELS, 500.0))
        self.assertFalse(stop.is_set())
        self.assertTrue(dll.closed)
        self.assertFalse(dll.cancelled.wait(0.2))

    def test_the_callers_stop_cancels_the_sdk_capture(self):
        dll = FakeDpfpdd(finger=False)
        stop = threading.Event()
        threading.Timer(0.2, stop.set).start()
        with self.assertRaises(CaptureCancelled):
            dpfpdd_reader(dll).capture(stop, 5)
        self.assertTrue(dll.closed)

    def test_two_captures_in_a_row_on_one_stop_both_work(self):
        dll = FakeDpfpdd(finger=True)
        reader = dpfpdd_reader(dll)
        stop = threading.Event()
        reader.capture(stop, 5)
        self.assertEqual(reader.capture(stop, 5).width, WIDTH)


class FakeWinBio:
    def __init__(self, finger: bool):
        self.finger = finger
        self.cancelled = threading.Event()
        self.closed = False
        self._keep = None

    def WinBioEnumBiometricUnits(self, kind, schemas, count):
        count._obj.value = 1
        return 0

    def WinBioFree(self, pointer):
        return 0

    def WinBioOpenSession(self, *args):
        return 0

    def WinBioCaptureSample(self, session, purpose, flags, unit, data, size, reject):
        if not self.finger:
            self.cancelled.wait(5)
            return WINBIO_E_CANCELED
        self._keep = ctypes.create_string_buffer(sample(), len(sample()))
        data._obj.value = ctypes.addressof(self._keep)
        size._obj.value = len(sample())
        return 0

    def WinBioCancel(self, session):
        self.cancelled.set()
        return 0

    def WinBioCloseSession(self, session):
        self.closed = True
        return 0


def winbio_reader(dll):
    reader = object.__new__(WinBioReader)
    reader._dll = dll
    reader._focus = False
    return reader


class WinBioCaptureTest(unittest.TestCase):
    def test_a_press_becomes_an_image_and_the_stop_is_left_alone(self):
        dll = FakeWinBio(finger=True)
        stop = threading.Event()
        capture = winbio_reader(dll).capture(stop, 5)
        self.assertEqual((capture.width, capture.height, capture.pixels), (WIDTH, HEIGHT, PIXELS))
        self.assertFalse(stop.is_set())
        self.assertTrue(dll.closed)
        self.assertFalse(dll.cancelled.wait(0.2))

    def test_the_callers_stop_cancels(self):
        dll = FakeWinBio(finger=False)
        stop = threading.Event()
        threading.Timer(0.2, stop.set).start()
        with self.assertRaises(CaptureCancelled):
            winbio_reader(dll).capture(stop, 5)

    def test_no_finger_before_the_timeout_is_a_timeout(self):
        with self.assertRaises(CaptureTimeout):
            winbio_reader(FakeWinBio(finger=False)).capture(threading.Event(), 0.2)

    def test_two_captures_in_a_row_on_one_stop_both_work(self):
        reader = winbio_reader(FakeWinBio(finger=True))
        stop = threading.Event()
        reader.capture(stop, 5)
        self.assertEqual(reader.capture(stop, 5).width, WIDTH)


if __name__ == "__main__":
    unittest.main()
