from pathlib import Path
import tempfile
import unittest

from PIL import Image

from plot2svg.analyze import analyze_image


class AnalyzeImageTest(unittest.TestCase):
    def test_analyze_image_routes_small_chart_even_when_filename_contains_signature(self) -> None:
        result = analyze_image(Path("picture/orr_signature.png"))
        self.assertEqual(result.route_type, "small_lowres")

    def test_analyze_image_routes_wide_sample(self) -> None:
        result = analyze_image(Path("picture/F2.png"))
        self.assertEqual(result.route_type, "wide_hires")

    def test_analyze_image_accepts_jpeg_input(self) -> None:
        image_path = Path(tempfile.gettempdir()) / "plot2svg_analyze_test.jpg"
        Image.new("RGB", (1200, 800), color="white").save(image_path, format="JPEG")

        result = analyze_image(image_path)

        self.assertEqual(result.width, 1200)
        self.assertEqual(result.height, 800)
        self.assertFalse(result.alpha_present)
        self.assertEqual(result.route_type, "flat_graphics")


if __name__ == "__main__":
    unittest.main()
