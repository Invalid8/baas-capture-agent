import ctypes
import unittest

from baas_capture_agent.reader import ReaderError
from baas_capture_agent.winbio import (
    E_ACCESSDENIED,
    SCALE_PPCM,
    SCALE_PPI,
    Ansi381Header,
    Ansi381Record,
    Bir,
    BirData,
    hresult_text,
    parse_sample,
)

WIDTH, HEIGHT = 6, 4
PIXELS = bytes(range(WIDTH * HEIGHT))


def sample(pixels=PIXELS, width=WIDTH, height=HEIGHT, depth=8, compression=0, resolution=500, scale=SCALE_PPI):
    header = Ansi381Header(
        pixel_depth=depth,
        image_compression_alg=compression,
        horizontal_image_resolution=resolution,
        vertical_image_resolution=resolution,
        scale_units=scale,
    )
    record = Ansi381Record(horizontal_line_length=width, vertical_line_length=height)
    standard = bytes(header) + bytes(record) + pixels
    bir = Bir(standard=BirData(size=len(standard), offset=ctypes.sizeof(Bir)))
    return bytes(bir) + standard


class LayoutTest(unittest.TestCase):
    def test_structures_match_the_windows_sdk_sizes(self):
        self.assertEqual(ctypes.sizeof(Bir), 32)
        self.assertEqual(ctypes.sizeof(Ansi381Header), 40)
        self.assertEqual(ctypes.sizeof(Ansi381Record), 16)


class ParseSampleTest(unittest.TestCase):
    def test_reads_the_image_and_its_resolution(self):
        capture = parse_sample(sample(), "4500")
        self.assertEqual((capture.width, capture.height, capture.pixels), (WIDTH, HEIGHT, PIXELS))
        self.assertEqual((capture.device, capture.ppi), ("4500", 500.0))

    def test_converts_pixels_per_centimetre(self):
        self.assertAlmostEqual(parse_sample(sample(resolution=197, scale=SCALE_PPCM), "4500").ppi, 500.38)

    def test_missing_resolution_is_none(self):
        self.assertIsNone(parse_sample(sample(resolution=0), "4500").ppi)

    def test_refuses_short_or_empty_samples(self):
        for data in (b"", sample()[:20], bytes(Bir())):
            with self.assertRaises(ReaderError):
                parse_sample(data, "4500")

    def test_refuses_a_cut_off_image(self):
        with self.assertRaisesRegex(ReaderError, "cut-off"):
            parse_sample(sample(pixels=PIXELS[:-3]), "4500")

    def test_refuses_images_it_cannot_encode(self):
        with self.assertRaisesRegex(ReaderError, "Unsupported"):
            parse_sample(sample(depth=16), "4500")
        with self.assertRaisesRegex(ReaderError, "Unsupported"):
            parse_sample(sample(compression=2), "4500")


class ErrorTextTest(unittest.TestCase):
    def test_names_known_errors_in_words(self):
        self.assertIn("Administrator", hresult_text(E_ACCESSDENIED))
        self.assertIn("Administrator", hresult_text(E_ACCESSDENIED - (1 << 32)))

    def test_unknown_errors_show_the_code(self):
        self.assertEqual(hresult_text(0x800106F7), "Windows biometric error 0x800106F7")


if __name__ == "__main__":
    unittest.main()
