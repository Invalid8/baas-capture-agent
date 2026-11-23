import ctypes
import threading
from ctypes import c_char, c_int, c_uint, c_uint16, c_void_p

from baas_capture_agent.reader import (
    BadPress,
    Capture,
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    OnFinger,
    ReaderError,
    ReaderStatus,
)

FACILITY = 0x05BA << 16
SUCCESS = 0
E_MORE_DATA = FACILITY | 13
E_INVALID_PARAMETER = FACILITY | 20
E_DEVICE_BUSY = FACILITY | 30
E_DEVICE_FAILURE = FACILITY | 31

QUALITY_TIMED_OUT = 1
QUALITY_CANCELED = 1 << 1
IMG_FMT_PIXEL_BUFFER = 0
IMG_PROC_NONE = 0
RESOLUTION = 500
MAX_READERS = 8
IMAGE_BUFFER = 1024 * 1024

DESCRIBED = {
    E_DEVICE_BUSY: "Another program is using the fingerprint reader",
    E_DEVICE_FAILURE: "The fingerprint reader is not working. Unplug it and plug it back in",
}


class VerInfo(ctypes.Structure):
    _fields_ = [("major", c_int), ("minor", c_int), ("maintenance", c_int)]


class DevInfo(ctypes.Structure):
    _fields_ = [
        ("size", c_uint),
        ("name", c_char * 1024),
        ("vendor_name", c_char * 128),
        ("product_name", c_char * 128),
        ("serial_num", c_char * 128),
        ("vendor_id", c_uint16),
        ("product_id", c_uint16),
        ("hw_ver", VerInfo),
        ("fw_ver", VerInfo),
        ("bcd_rev", c_uint16),
        ("modality", c_uint),
        ("technology", c_uint),
    ]


class CaptureParam(ctypes.Structure):
    _fields_ = [("size", c_uint), ("image_fmt", c_uint), ("image_proc", c_uint), ("image_res", c_uint)]


class ImageInfo(ctypes.Structure):
    _fields_ = [("size", c_uint), ("width", c_uint), ("height", c_uint), ("res", c_uint), ("bpp", c_uint)]


class CaptureResult(ctypes.Structure):
    _fields_ = [("size", c_uint), ("success", c_int), ("quality", c_uint), ("score", c_uint), ("info", ImageInfo)]


def error_text(code: int) -> str:
    code &= 0xFFFFFFFF
    return DESCRIBED.get(code, f"DigitalPersona reader error 0x{code:08X}")


def capture_from(result: CaptureResult, image: bytes, device: str) -> Capture:
    """Turn one dpfpdd_capture answer into a Capture, or say what to do instead."""
    if result.quality & QUALITY_CANCELED:
        raise CaptureCancelled("Capture cancelled")
    if result.quality & QUALITY_TIMED_OUT:
        raise CaptureTimeout("No finger detected")
    if not result.success:
        raise BadPress("The reader could not read that press")
    info = result.info
    if info.bpp != 8:
        raise ReaderError(f"Unsupported image: {info.bpp}-bit")
    pixels = image[: info.width * info.height]
    if info.width == 0 or info.height == 0 or len(pixels) != info.width * info.height:
        raise ReaderError("The reader returned a cut-off image")
    return Capture(width=info.width, height=info.height, pixels=pixels, device=device, ppi=float(info.res) or None)


class DpfpddReader:
    """U.are.U 4500 through the U.are.U SDK runtime (dpfpdd.dll) and DigitalPersona's own (non-WBF) driver,
    so PCs that already use the SDK keep it. The reader is held only while a capture runs."""

    def __init__(self):
        self._dll = ctypes.WinDLL("dpfpdd.dll")
        self._dll.dpfpdd_capture.argtypes = [
            c_void_p, ctypes.POINTER(CaptureParam), c_uint, ctypes.POINTER(CaptureResult),
            ctypes.POINTER(c_uint), ctypes.c_char_p,
        ]
        result = self._dll.dpfpdd_init() & 0xFFFFFFFF
        if result != SUCCESS:
            raise OSError(error_text(result))

    def _readers(self) -> list[DevInfo]:
        infos = (DevInfo * MAX_READERS)()
        for info in infos:
            info.size = ctypes.sizeof(DevInfo)
        count = c_uint(MAX_READERS)
        if self._dll.dpfpdd_query_devices(ctypes.byref(count), infos) & 0xFFFFFFFF != SUCCESS:
            return []
        return list(infos[: count.value])

    def _describe(self, info: DevInfo) -> str:
        return info.product_name.decode(errors="replace").strip() or "U.are.U reader"

    def status(self) -> ReaderStatus:
        readers = self._readers()
        if not readers:
            return ReaderStatus(connected=False)
        return ReaderStatus(connected=True, device=f"{self._describe(readers[0])} (U.are.U SDK)", driver="dpfpdd")

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        readers = self._readers()
        if not readers:
            raise NoReaderError("Fingerprint reader not connected")
        device = c_void_p()
        opened = self._dll.dpfpdd_open(readers[0].name, ctypes.byref(device)) & 0xFFFFFFFF
        if opened != SUCCESS:
            raise ReaderError(error_text(opened))

        def watch():
            if stop.wait(timeout):
                self._dll.dpfpdd_cancel(device)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        param = CaptureParam(ctypes.sizeof(CaptureParam), IMG_FMT_PIXEL_BUFFER, IMG_PROC_NONE, RESOLUTION)
        result = CaptureResult(size=ctypes.sizeof(CaptureResult))
        result.info.size = ctypes.sizeof(ImageInfo)
        size = c_uint(IMAGE_BUFFER)
        image = ctypes.create_string_buffer(IMAGE_BUFFER)
        try:
            code = self._dll.dpfpdd_capture(
                device, ctypes.byref(param), c_uint(max(1, int(timeout * 1000))), ctypes.byref(result),
                ctypes.byref(size), image,
            ) & 0xFFFFFFFF
            if code != SUCCESS:
                raise ReaderError(error_text(code))
            return capture_from(result, image.raw[: size.value], f"{self._describe(readers[0])} (U.are.U SDK)")
        finally:
            stop.set()
            self._dll.dpfpdd_close(device)
