from pathlib import Path
import tempfile
import unittest

from PIL import Image

from plot2svg.analyze import analyze_image
from plot2svg.config import PipelineConfig, ThresholdConfig


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

    def test_analyze_image_respects_custom_small_route_threshold(self) -> None:
        image_path = Path(tempfile.gettempdir()) / "plot2svg_analyze_small_route.jpg"
        output_dir = Path(tempfile.gettempdir()) / "plot2svg-analyze-small-route"
        Image.new("RGB", (1200, 800), color="white").save(image_path, format="JPEG")
        cfg = PipelineConfig(
            input_path=image_path,
            output_dir=output_dir,
            thresholds=ThresholdConfig(analyze_route_small_max_side=1400),
        )

        result = analyze_image(image_path, cfg=cfg)

        self.assertEqual(result.route_type, "small_lowres")

    def test_analyze_image_respects_custom_signature_thresholds(self) -> None:
        image_path = Path(tempfile.gettempdir()) / "plot2svg_custom_signature_route.png"
        output_dir = Path(tempfile.gettempdir()) / "plot2svg-analyze-signature-route"
        image = Image.new("RGB", (1200, 800), color="white")
        for x in range(1200):
            for y in range(200):
                image.putpixel((x, y), (0, 0, 0))
        image.save(image_path, format="PNG")
        cfg = PipelineConfig(
            input_path=image_path,
            output_dir=output_dir,
            thresholds=ThresholdConfig(analyze_signature_dark_ratio_max=0.30),
        )

        result = analyze_image(image_path, cfg=cfg)

        self.assertEqual(result.route_type, "signature_lineart")


if __name__ == "__main__":
    unittest.main()
