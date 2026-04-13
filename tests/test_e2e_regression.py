from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from plot2svg.analyze import analyze_image
from plot2svg.api import Plot2SvgEngine
from tests.e2e_utils import load_regression_snapshot, run_pipeline_summary_isolated, sample_image_path
from tests.e2e_utils import generated_input_path


class E2ERegressionTest(unittest.TestCase):
    def test_regression_samples_match_golden_snapshot(self) -> None:
        snapshot = load_regression_snapshot()
        self.assertTrue(snapshot)

        current = {
            image_name: run_pipeline_summary_isolated(sample_image_path(image_name))
            for image_name in snapshot
        }

        for image_name, summary in current.items():
            self.assertEqual(summary["status"], "ok", image_name)
            self.assertTrue(summary["has_shape_data"], image_name)

        self.assertEqual(current, snapshot)

    def test_blank_image_pipeline_keeps_minimal_scene(self) -> None:
        image_path = generated_input_path("blank_input.png")
        Image.new("RGB", (256, 256), color="white").save(image_path, format="PNG")

        summary = run_pipeline_summary_isolated(image_path)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["text_count"], 0)
        self.assertGreaterEqual(summary["region_count"], 1)
        self.assertEqual(summary["graph_edge_count"], 0)

    def test_large_image_sets_tiling_gate(self) -> None:
        image_path = generated_input_path("large_input.png")
        Image.new("RGB", (5000, 1200), color="white").save(image_path, format="PNG")

        result = analyze_image(image_path)

        self.assertTrue(result.should_tile)
        self.assertEqual(result.route_type, "wide_hires")

    def test_text_only_image_preserves_text_nodes(self) -> None:
        image_path = generated_input_path("text_only_input.png")
        image = Image.new("RGB", (640, 320), color="white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 60), "Plot2SVG Phase 3", fill="black")
        draw.text((40, 140), "Regression baseline text-only sample", fill="black")
        image.save(image_path, format="PNG")

        summary = run_pipeline_summary_isolated(image_path)

        self.assertEqual(summary["status"], "ok")
        self.assertGreaterEqual(summary["text_count"], 1)
        self.assertEqual(summary["graph_edge_count"], 0)

    def test_engine_reports_error_for_invalid_input(self) -> None:
        bad_path = generated_input_path("invalid_input.txt")
        bad_path.write_text("not an image", encoding="utf-8")
        output_dir = Path(tempfile.gettempdir()) / "plot2svg-invalid-input-output"
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = Plot2SvgEngine().process_image(image_path=bad_path, output_dir=output_dir)

        self.assertEqual(payload["status"], "error")
        self.assertIn("Unsupported image format", payload["error"]["message"])
