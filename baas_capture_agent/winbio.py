import ctypes
import threading
from ctypes import c_uint8, c_uint16, c_uint32, c_uint64

from baas_capture_agent.reader import (
    BadPress,
    Capture,
    CaptureCancelled,
    CaptureTimeout,
    NoReaderError,
    ReaderError,
    OnFinger,
    ReaderStatus,
    Watch,
)

WINBIO_TYPE_FINGERPRINT = 0x00000008
WINBIO_POOL_SYSTEM = 1
WINBIO_FLAG_RAW = 0x00000001
WINBIO_DB_DEFAULT = 1
WINBIO_NO_PURPOSE_AVAILABLE = 0
WINBIO_DATA_FLAG_RAW = 0x20

E_ACCESSDENIED = 0x80070005
WINBIO_E_NO_CAPTURE_DATA = 0x80098009
WINBIO_E_CANCELED = 0x80098004
WINBIO_E_BAD_CAPTURE = 0x80098008
WINBIO_E_UNKNOWN_ID = 0x80098005
WINBIO_E_INVALID_UNIT = 0x8009800A
WINBIO_E_DEVICE_BUSY = 0x80098006

SCALE_PPI = 1
SCALE_PPCM = 2

DESCRIBED = {
    E_ACCESSDENIED: "Windows refused raw fingerprint images: run the agent as Administrator",
    WINBIO_E_BAD_CAPTURE: "The reader could not read that press",
    WINBIO_E_CANCELED: "Capture cancelled",
    WINBIO_E_DEVICE_BUSY: "Another program is using the fingerprint reader",
    WINBIO_E_INVALID_UNIT: "Fingerprint reader not connected",
    WINBIO_E_NO_CAPTURE_DATA: "The reader returned no image",
}


class BirData(ctypes.Structure):
    _fields_ = [("size", c_uint32), ("offset", c_uint32)]


class Bir(ctypes.Structure):
    _fields_ = [("header", BirData), ("standard", BirData), ("vendor", BirData), ("signature", BirData)]


class Ansi381Header(ctypes.Structure):
    _fields_ = [
        ("record_length", c_uint64),
        ("format_identifier", c_uint32),
        ("version_number", c_uint32),
        ("product_owner", c_uint16),
        ("product_type", c_uint16),
        ("capture_device_id", c_uint16),
        ("image_acquisition_level", c_uint16),
        ("horizontal_scan_resolution", c_uint16),
        ("vertical_scan_resolution", c_uint16),
        ("horizontal_image_resolution", c_uint16),
        ("vertical_image_resolution", c_uint16),
        ("element_count", c_uint8),
        ("scale_units", c_uint8),
        ("pixel_depth", c_uint8),
        ("image_compression_alg", c_uint8),
        ("reserved", c_uint16),
    ]


class Ansi381Record(ctypes.Structure):
    _fields_ = [
        ("block_length", c_uint32),
        ("horizontal_line_length", c_uint16),
        ("vertical_line_length", c_uint16),
        ("position", c_uint8),
        ("count_of_views", c_uint8),
        ("view_number", c_uint8),
        ("image_quality", c_uint8),
        ("impression_type", c_uint8),
        ("reserved", c_uint8),
    ]


def hresult_text(code: int) -> str:
    code &= 0xFFFFFFFF
    return DESCRIBED.get(code, f"Windows biometric error 0x{code:08X}")


def parse_sample(sample: bytes, device: str) -> Capture:
    if len(sample) < ctypes.sizeof(Bir):
        raise ReaderError("The reader returned a sample that is too short")
    bir = Bir.from_buffer_copy(sample)
    start, size = bir.standard.offset, bir.standard.size
    header_end = start + ctypes.sizeof(Ansi381Header)
    record_end = header_end + ctypes.sizeof(Ansi381Record)
    if size == 0 or record_end > len(sample):
        raise ReaderError("The reader returned no image")
    header = Ansi381Header.from_buffer_copy(sample, start)
    record = Ansi381Record.from_buffer_copy(sample, header_end)
    if header.pixel_depth != 8 or header.image_compression_alg != 0:
        raise ReaderError(
            f"Unsupported image: {header.pixel_depth}-bit, compression {header.image_compression_alg}"
        )
    width, height = record.horizontal_line_length, record.vertical_line_length
    pixels = sample[record_end : record_end + width * height]
    if width == 0 or height == 0 or len(pixels) != width * height:
        raise ReaderError("The reader returned a cut-off image")
    resolution = header.horizontal_image_resolution
    ppi = resolution * 2.54 if header.scale_units == SCALE_PPCM else float(resolution)
    return Capture(width=width, height=height, pixels=bytes(pixels), device=device, ppi=ppi or None)


class WinBioReader:
    """U.are.U 4500 through the Windows Biometric Framework (the 4500's WBF driver)."""

    DEVICE = "U.are.U 4500 (Windows Biometric Framework)"

    def __init__(self, focus: bool = True):
        self._dll = ctypes.WinDLL("winbio.dll")
        self._focus = focus

    def _check(self, result: int, missing_is_unplugged: bool = False):
        code = result & 0xFFFFFFFF
        if code == 0:
            return
        if code == WINBIO_E_CANCELED:
            raise CaptureCancelled("Capture cancelled")
        if code == WINBIO_E_BAD_CAPTURE:
            raise BadPress(hresult_text(code))
        if missing_is_unplugged and code == WINBIO_E_INVALID_UNIT:
            raise NoReaderError("Fingerprint reader not connected")
        raise ReaderError(hresult_text(code))

    def _open(self) -> ctypes.c_uint32:
        session = c_uint32()
        self._check(
            self._dll.WinBioOpenSession(
                c_uint32(WINBIO_TYPE_FINGERPRINT),
                c_uint32(WINBIO_POOL_SYSTEM),
                c_uint32(WINBIO_FLAG_RAW),
                None,
                ctypes.c_size_t(0),
                ctypes.c_void_p(WINBIO_DB_DEFAULT),
                ctypes.byref(session),
            ),
            missing_is_unplugged=True,
        )
        return session

    def unit_count(self) -> int:
        schemas = ctypes.c_void_p()
        count = ctypes.c_size_t()
        self._check(
            self._dll.WinBioEnumBiometricUnits(
                c_uint32(WINBIO_TYPE_FINGERPRINT), ctypes.byref(schemas), ctypes.byref(count)
            )
        )
        if schemas:
            self._dll.WinBioFree(schemas)
        return count.value

    def status(self) -> ReaderStatus:
        try:
            connected = self.unit_count() > 0
        except ReaderError:
            connected = False
        if not connected:
            return ReaderStatus(connected=False)
        return ReaderStatus(connected=True, device=self.DEVICE, driver="winbio")

    def capture(self, stop: threading.Event, timeout: float, on_finger: OnFinger = None) -> Capture:
        if self.unit_count() == 0:
            raise NoReaderError("Fingerprint reader not connected")
        session = self._open()
        focused = self._focus and self._dll.WinBioAcquireFocus() & 0xFFFFFFFF == 0
        watch = Watch(stop, timeout, lambda: self._dll.WinBioCancel(session))
        sample = ctypes.c_void_p()
        size = ctypes.c_size_t()
        unit = c_uint32()
        reject = c_uint32()
        try:
            result = self._dll.WinBioCaptureSample(
                session,
                c_uint8(WINBIO_NO_PURPOSE_AVAILABLE),
                c_uint8(WINBIO_DATA_FLAG_RAW),
                ctypes.byref(unit),
                ctypes.byref(sample),
                ctypes.byref(size),
                ctypes.byref(reject),
            )
            if result & 0xFFFFFFFF == WINBIO_E_CANCELED and watch.reason == "timeout":
                raise CaptureTimeout("No finger detected")
            self._check(result)
            data = ctypes.string_at(sample, size.value)
        finally:
            watch.done()
            if sample:
                self._dll.WinBioFree(sample)
            if focused:
                self._dll.WinBioReleaseFocus()
            self._dll.WinBioCloseSession(session)
        return parse_sample(data, self.DEVICE)
