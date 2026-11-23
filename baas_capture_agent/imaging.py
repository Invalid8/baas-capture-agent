from dataclasses import dataclass

STANDARD_PPI = 500.0
BLOCK = 16
BLOCK_CONTRAST = 20.0
BLANK_INK = 0.003
MIN_INK = 0.015
MIN_COVERAGE = 0.35


@dataclass(frozen=True)
class Image:
    width: int
    height: int
    pixels: bytes


@dataclass(frozen=True)
class Assessment:
    ink: float
    coverage: float
    problem: str | None

    @property
    def ok(self) -> bool:
        return self.problem is None


def to_standard(image: Image, ppi: float | None) -> Image:
    if not ppi or abs(ppi - STANDARD_PPI) < 1:
        return image
    scale = STANDARD_PPI / ppi
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    src, sw, sh = image.pixels, image.width, image.height
    out = bytearray(width * height)
    for y in range(height):
        fy = min(max((y + 0.5) / scale - 0.5, 0.0), sh - 1.0)
        y0 = int(fy)
        y1 = min(y0 + 1, sh - 1)
        wy = fy - y0
        row0, row1 = y0 * sw, y1 * sw
        for x in range(width):
            fx = min(max((x + 0.5) / scale - 0.5, 0.0), sw - 1.0)
            x0 = int(fx)
            x1 = min(x0 + 1, sw - 1)
            wx = fx - x0
            top = src[row0 + x0] * (1 - wx) + src[row0 + x1] * wx
            bottom = src[row1 + x0] * (1 - wx) + src[row1 + x1] * wx
            out[y * width + x] = round(top * (1 - wy) + bottom * wy)
    return Image(width, height, bytes(out))


def _median(pixels: bytes) -> int:
    counts = [0] * 256
    for p in pixels:
        counts[p] += 1
    half, seen = len(pixels) / 2, 0
    for value, n in enumerate(counts):
        seen += n
        if seen >= half:
            return value
    return 255


def assess(image: Image) -> Assessment:
    pixels, width, height = image.pixels, image.width, image.height
    light_background = _median(pixels) >= 128
    ink = sum(1 for p in pixels if (p < 128) == light_background) / len(pixels)

    blocks = busy = 0
    for top in range(0, height - BLOCK + 1, BLOCK):
        for left in range(0, width - BLOCK + 1, BLOCK):
            values = [pixels[(top + dy) * width + left + dx] for dy in range(BLOCK) for dx in range(BLOCK)]
            mean = sum(values) / len(values)
            spread = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
            blocks += 1
            busy += spread >= BLOCK_CONTRAST
    coverage = busy / blocks if blocks else 0.0
    return Assessment(ink=round(ink, 4), coverage=round(coverage, 3), problem=verdict(ink, coverage))


def verdict(ink: float, coverage: float) -> str | None:
    """Thresholds from real U.are.U 4500 presses (23 Nov 2026): empty glass and a barely
    touching tip ~0.1% ink; half a finger 0.4-1% ink; full presses 2-16% ink, 39-79% area."""
    if ink < BLANK_INK:
        return "blank"
    if ink < MIN_INK or coverage < MIN_COVERAGE:
        return "faint"
    return None
