import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Protocol

OnFinger = Callable[[str], None] | None


class ReaderError(Exception):
    pass


class NoReaderError(ReaderError):
    pass


class CaptureCancelled(ReaderError):
    pass


class CaptureTimeout(ReaderError):
    pass


class BadPress(ReaderError):
    """The reader saw a finger but couldn't read it; the agent asks for another press."""


@dataclass(frozen=True)
class Capture:
    width: int
    height: int
    pixels: bytes
    device: str
    ppi: float | None = None


@dataclass(frozen=True)
class ReaderStatus:
    connected: bool
    device: str | None = None
    driver: str | None = None


class Reader(Protocol):
    def status(self) -> ReaderStatus: ...

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture: ...


class UnavailableReader:
    """Stands in when the system has no way to reach a reader, so the agent and its check page still run."""

    def __init__(self, reason: str):
        self.reason = reason

    def status(self) -> ReaderStatus:
        return ReaderStatus(connected=False)

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        raise NoReaderError(self.reason)


class FirstConnected:
    """Several ways to reach the reader (Windows: its own framework, then the U.are.U SDK); uses whichever sees it."""

    def __init__(self, readers: list[Reader]):
        self.readers = readers

    def _connected(self) -> tuple[Reader, ReaderStatus] | None:
        for reader in self.readers:
            status = reader.status()
            if status.connected:
                return reader, status
        return None

    def status(self) -> ReaderStatus:
        found = self._connected()
        return found[1] if found else ReaderStatus(connected=False)

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        found = self._connected()
        if found is None:
            raise NoReaderError("Fingerprint reader not connected")
        return found[0].capture(stop, timeout, on_finger)


def restart_agent(reason: str) -> None:
    """libfprint keeps a replugged reader as a dead device and can't make a second context in one
    process, so the agent starts itself again (about a second) to see the reader afresh."""
    print(f"restarting: {reason}", flush=True)
    os.execv(sys.executable, [sys.executable, "-m", "baas_capture_agent", *sys.argv[1:]])


class LibfprintReader:
    """U.are.U 4500 (libfprint 'uru4000' driver) through GObject introspection."""

    def __init__(self):
        import gi

        gi.require_version("FPrint", "2.0")
        from gi.repository import FPrint, Gio, GLib

        self._fprint, self._gio, self._glib = FPrint, Gio, GLib
        self._context = FPrint.Context()
        self._plugged: tuple[str, ...] = ()

    def _capture_device(self):
        from baas_capture_agent.doctor import plugged_readers

        plugged = plugged_readers()
        if not plugged:
            return None
        if self._plugged and plugged != self._plugged:
            restart_agent("the fingerprint reader was plugged back in")
        self._plugged = plugged
        self._context.enumerate()
        main_context = self._glib.MainContext.default()
        while main_context.iteration(False):
            pass
        for device in self._context.get_devices():
            if device.has_feature(self._fprint.DeviceFeature.CAPTURE):
                return device
        return None

    def status(self) -> ReaderStatus:
        device = self._capture_device()
        if device is None:
            return ReaderStatus(connected=False)
        return ReaderStatus(connected=True, device=device.get_name(), driver=device.get_driver())

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        device = self._capture_device()
        if device is None:
            raise NoReaderError("Fingerprint reader not connected")

        cancellable = self._gio.Cancellable()
        reason: list[str] = []

        def watch():
            reason.append("cancelled" if stop.wait(timeout) else "timeout")
            cancellable.cancel()

        try:
            device.open_sync(None)
        except self._glib.Error as exc:
            raise ReaderError(exc.message) from exc
        flags = self._fprint.FingerStatusFlags
        told: set[str] = set()

        def finger_status(dev, _spec):
            if on_finger is None:
                return
            status = dev.get_finger_status()
            if not status & flags.PRESENT:
                return
            moment = "on" if status & flags.NEEDED else "captured"
            if moment not in told:
                told.add(moment)
                on_finger(moment)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        handler = device.connect("notify::finger-status", finger_status)
        try:
            image = device.capture_sync(True, cancellable)
        except self._glib.Error as exc:
            if cancellable.is_cancelled():
                if reason and reason[0] == "timeout":
                    raise CaptureTimeout("No finger detected") from exc
                raise CaptureCancelled("Capture cancelled") from exc
            raise ReaderError(exc.message) from exc
        finally:
            device.disconnect(handler)
            stop.set()
            device.close_sync(None)

        return Capture(
            width=image.get_width(),
            height=image.get_height(),
            pixels=bytes(image.get_data()),
            device=device.get_name(),
            ppi=image.get_ppmm() * 25.4,
        )
