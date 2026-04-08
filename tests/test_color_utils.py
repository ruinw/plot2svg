import unittest

from plot2svg.color_utils import _bgr_to_hex, _hex_to_bgr, _is_dark_color, _is_light_hex


class ColorUtilsTest(unittest.TestCase):
    def test_bgr_hex_round_trip(self) -> None:
        color = (16, 32, 48)

        hex_color = _bgr_to_hex(color)

        self.assertEqual(hex_color, '#302010')
        self.assertEqual(_hex_to_bgr(hex_color), color)

    def test_light_and_dark_color_predicates(self) -> None:
        self.assertTrue(_is_light_hex('#f0e0f0'))
        self.assertFalse(_is_light_hex('#101010'))
        self.assertTrue(_is_dark_color('#101010'))
        self.assertFalse(_is_dark_color('#f0e0f0'))


if __name__ == "__main__":
    unittest.main()
