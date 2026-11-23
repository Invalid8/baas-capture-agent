import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from baas_capture_agent.reader import Capture, CaptureCancelled, NeedsFreshStart, NoReaderError, ReaderStatus
from baas_capture_agent.worker import WorkerReader

os.environ.setdefault("BAAS_WORKER_TEST_MARK", str(Path(tempfile.gettempdir()) / f"baas-worker-test-{os.getpid()}"))
MARK = Path(os.environ["BAAS_WORKER_TEST_MARK"])


class FakeReader:
    def status(self):
        return ReaderStatus(connected=True, device="fake 4500", driver="fake")

    def capture(self, stop, timeout, on_finger=None):
        if on_finger:
            on_finger("on")
            on_finger("captured")
        return Capture(2, 1, b"\x10\x20", "fake 4500", 500.0)


class SlowReader(FakeReader):
    def capture(self, stop, timeout, on_finger=None):
        if stop.wait(timeout):
            raise CaptureCancelled("Capture cancelled")
        return super().capture(stop, timeout, on_finger)


class HotOnceReader(FakeReader):
    """Needs a fresh start the first time; the mark file tells the next helper it already happened."""

    def capture(self, stop, timeout, on_finger=None):
        if not MARK.exists():
            MARK.write_text("hot")
            raise NeedsFreshStart("heat timer")
        return super().capture(stop, timeout, on_finger)


class AlwaysHotReader(FakeReader):
    def capture(self, stop, timeout, on_finger=None):
        raise NeedsFreshStart("heat timer")


class DyingReader(FakeReader):
    def status(self):
        os._exit(1)


class WorkerTest(unittest.TestCase):
    def worker(self, make):
        w = WorkerReader(make)
        self.addCleanup(lambda: w._process.kill())
        return w

    def test_status_and_capture_come_from_the_helper(self):
        w = self.worker(FakeReader)
        moments = []
        self.assertEqual(w.status().device, "fake 4500")
        capture = w.capture(threading.Event(), 5, on_finger=moments.append)
        self.assertEqual((capture.width, capture.pixels, capture.ppi), (2, b"\x10\x20", 500.0))
        self.assertEqual(moments, ["on", "captured"])

    def test_a_capture_can_be_cancelled(self):
        w = self.worker(SlowReader)
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        started = time.monotonic()
        with self.assertRaises(CaptureCancelled):
            w.capture(stop, 30)
        self.assertLess(time.monotonic() - started, 5)

    def test_status_while_capturing_does_not_wait(self):
        w = self.worker(SlowReader)
        w.status()
        stop = threading.Event()
        threading.Thread(target=lambda: self.assertRaises(CaptureCancelled, w.capture, stop, 30)).start()
        time.sleep(0.3)
        started = time.monotonic()
        self.assertTrue(w.status().connected)
        self.assertLess(time.monotonic() - started, 0.2)
        stop.set()

    def test_a_reader_that_needs_a_fresh_start_gets_one_and_the_capture_still_succeeds(self):
        MARK.unlink(missing_ok=True)
        self.addCleanup(lambda: MARK.unlink(missing_ok=True))
        w = self.worker(HotOnceReader)
        capture = w.capture(threading.Event(), 5)
        self.assertEqual(capture.device, "fake 4500")
        self.assertEqual(w.fresh_starts, 1)

    def test_it_gives_up_rather_than_restarting_forever(self):
        w = self.worker(AlwaysHotReader)
        with self.assertRaises(NoReaderError):
            w.capture(threading.Event(), 5)
        self.assertEqual(w.fresh_starts, 2)

    def test_a_helper_that_dies_is_replaced(self):
        w = self.worker(DyingReader)
        self.assertFalse(w.status().connected)
        self.assertGreaterEqual(w.fresh_starts, 1)


if __name__ == "__main__":
    unittest.main()
