import unittest

from baas_capture_agent.imaging import Image, assess, to_standard, verdict


def ridges(width, height, period=8, dark=30, light=220, background=235, inset=0):
    pixels = bytearray([background] * (width * height))
    for y in range(inset, height - inset):
        for x in range(inset, width - inset):
            pixels[y * width + x] = dark if (x // (period // 2)) % 2 == 0 else light
    return Image(width, height, bytes(pixels))


class StandardTest(unittest.TestCase):
    def test_500_ppi_images_pass_through_unchanged(self):
        image = ridges(32, 24)
        self.assertIs(to_standard(image, 500.0), image)
        self.assertIs(to_standard(image, None), image)

    def test_512_ppi_is_scaled_down_to_500(self):
        out = to_standard(ridges(384, 290), 512.0)
        self.assertEqual((out.width, out.height), (375, 283))
        self.assertEqual(len(out.pixels), 375 * 283)

    def test_a_flat_image_stays_flat(self):
        flat = Image(10, 10, bytes([200] * 100))
        self.assertEqual(set(to_standard(flat, 400.0).pixels), {200})

    def test_scaling_keeps_the_ends_of_a_gradient(self):
        row = bytes(range(0, 250, 10))
        out = to_standard(Image(len(row), 1, row), 250.0)
        self.assertEqual((out.pixels[0], out.pixels[-1]), (0, 240))


class AssessTest(unittest.TestCase):
    def test_a_full_print_passes(self):
        result = assess(ridges(128, 128))
        self.assertTrue(result.ok)
        self.assertGreater(result.ink, 0.3)
        self.assertEqual(result.coverage, 1.0)

    def test_an_empty_glass_is_blank(self):
        result = assess(Image(64, 64, bytes([235] * 64 * 64)))
        self.assertEqual(result.problem, "blank")

    def test_a_latent_smudge_is_blank(self):
        pixels = bytearray([235] * 128 * 128)
        for i in range(0, 12):
            pixels[i * 129] = 20
        self.assertEqual(assess(Image(128, 128, bytes(pixels))).problem, "blank")

    def test_a_low_contrast_press_is_faint(self):
        self.assertEqual(assess(ridges(128, 128, dark=120, light=140, background=140)).problem, "faint")

    def test_a_tip_touching_one_corner_is_faint(self):
        image = ridges(128, 128, inset=0)
        pixels = bytearray([235] * 128 * 128)
        for y in range(16):
            pixels[y * 128 : y * 128 + 32] = image.pixels[y * 128 : y * 128 + 32]
        self.assertEqual(assess(Image(128, 128, bytes(pixels))).problem, "faint")

    def test_thresholds_match_the_real_4500_presses_of_23_nov(self):
        cases = {
            "firm press": (0.055, 0.67, None),
            "lowest real press": (0.020, 0.39, None),
            "light fingertip": (0.0008, 0.05, "blank"),
            "half on the glass": (0.010, 0.45, "faint"),
            "half, lighter": (0.004, 0.33, "faint"),
        }
        for name, (ink, coverage, problem) in cases.items():
            self.assertEqual(verdict(ink, coverage), problem, name)

    def test_a_dark_background_image_is_read_the_other_way_round(self):
        image = ridges(128, 128)
        inverted = Image(128, 128, bytes(255 - p for p in image.pixels))
        self.assertEqual(assess(inverted).ink, assess(image).ink)


if __name__ == "__main__":
    unittest.main()
