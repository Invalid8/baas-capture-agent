"""Runs libfprint in a helper process the agent can replace in about half a second.

libfprint keeps a replugged reader as a dead device, can't open a second context in one process, and
switches a reader off after about three minutes of use by a generic heat timer. A fresh process clears
all three, while the agent's web side stays up and the person at the screen sees no outage.
"""

import multiprocessing
import threading
from typing import Callable

from baas_capture_agent import reader as readers
from baas_capture_agent.reader import (
    Capture,
    NeedsFreshStart,
    NoReaderError,
    OnFinger,
    ReaderError,
    ReaderStatus,
)

ERRORS = {
    cls.__name__: cls
    for cls in (
        readers.ReaderError,
        readers.NoReaderError,
        readers.CaptureCancelled,
        readers.CaptureTimeout,
        readers.BadPress,
        readers.NeedsFreshStart,
    )
}
FRESH_STARTS = 2


def serve(conn, make_reader: Callable[[], readers.Reader]) -> None:
    """The helper process: one reader, commands in, answers and finger events out."""
    reader = make_reader()
    send_lock = threading.Lock()
    stop = threading.Event()

    def send(message):
        with send_lock:
            conn.send(message)

    def capture(timeout: float):
        try:
            result = reader.capture(stop, timeout, on_finger=lambda moment: send(("finger", moment)))
            send(("captured", result))
        except ReaderError as exc:
            send(("error", type(exc).__name__, str(exc)))

    while True:
        try:
            command = conn.recv()
        except EOFError:
            return
        kind = command[0]
        if kind == "status":
            try:
                send(("status", reader.status()))
            except ReaderError as exc:
                send(("error", type(exc).__name__, str(exc)))
        elif kind == "capture":
            stop.clear()
            threading.Thread(target=capture, args=(command[1],), daemon=True).start()
        elif kind == "cancel":
            stop.set()


class WorkerReader:
    """A Reader whose libfprint lives in a helper process that is replaced when it needs a fresh start."""

    def __init__(self, make_reader: Callable[[], readers.Reader]):
        self._make_reader = make_reader
        self._context = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._busy = threading.Event()
        self._last = ReaderStatus(connected=False)
        self.fresh_starts = 0
        self._start()

    def _start(self) -> None:
        self._conn, child = self._context.Pipe()
        self._process = self._context.Process(target=serve, args=(child, self._make_reader), daemon=True)
        self._process.start()
        child.close()

    def fresh_start(self) -> None:
        self._process.kill()
        self._process.join(5)
        self._conn.close()
        self.fresh_starts += 1
        self._start()

    def _answer(self):
        try:
            return self._conn.recv()
        except (EOFError, OSError):
            return ("error", "NeedsFreshStart", "the reader helper stopped")

    def _raise(self, name: str, message: str):
        raise ERRORS.get(name, ReaderError)(message)

    def status(self) -> ReaderStatus:
        if self._busy.is_set():
            return self._last
        with self._lock:
            for _ in range(FRESH_STARTS):
                self._conn.send(("status",))
                answer = self._answer()
                if answer[0] == "status":
                    self._last = answer[1]
                    return self._last
                if answer[1] != "NeedsFreshStart":
                    break
                self.fresh_start()
        return ReaderStatus(connected=False)

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        with self._lock:
            self._busy.set()
            try:
                for _ in range(FRESH_STARTS):
                    try:
                        return self._capture_once(stop, timeout, on_finger)
                    except NeedsFreshStart:
                        self.fresh_start()
                raise NoReaderError("Fingerprint reader not connected")
            finally:
                self._busy.clear()

    def _capture_once(self, stop: threading.Event, timeout: float, on_finger: OnFinger) -> Capture:
        self._conn.send(("capture", timeout))
        done = threading.Event()

        def relay_cancel():
            while not done.is_set():
                if stop.wait(0.1) and not done.is_set():
                    self._conn.send(("cancel",))
                    return

        threading.Thread(target=relay_cancel, daemon=True).start()
        try:
            while True:
                answer = self._answer()
                if answer[0] == "finger":
                    if on_finger:
                        on_finger(answer[1])
                elif answer[0] == "captured":
                    return answer[1]
                else:
                    self._raise(answer[1], answer[2])
        finally:
            done.set()
