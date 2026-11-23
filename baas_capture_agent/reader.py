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


class LibfprintReader:
    """U.are.U 4500 (libfprint 'uru4000' driver) through GObject introspection."""

    def __init__(self):
        import gi

        gi.require_version("FPrint", "2.0")
        from gi.repository import FPrint, Gio, GLib

        self._fprint, self._gio, self._glib = FPrint, Gio, GLib
        self._context = FPrint.Context()

    def _capture_device(self):
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
