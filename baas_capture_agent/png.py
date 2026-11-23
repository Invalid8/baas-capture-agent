import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def encode_grayscale(pixels: bytes, width: int, height: int) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("Image must have a positive size")
    if len(pixels) != width * height:
        raise ValueError(f"Expected {width * height} bytes of 8-bit grey, got {len(pixels)}")
    rows = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        _SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 6))
        + _chunk(b"IEND", b"")
    )
