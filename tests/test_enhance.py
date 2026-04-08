from pathlib import Path
import shutil
import unittest

from plot2svg.analyze import AnalysisResult
from plot2svg.config import PipelineConfig
from plot2svg.enhance import EnhancementPlan, enhance_image


class EnhanceTest(unittest.TestCase):
    def test_enhancement_plan_skips_super_resolution_for_wide_hires(self) -> None:
        plan = EnhancementPlan.from_route("wide_hires", requested_mode="auto")
        self.assertFalse(plan.use_super_resolution)

    def test_enhance_image_creates_expected_artifacts(self) -> None:
        output_dir = Path("outputs/test-enhance")
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=output_dir)
        analysis = AnalysisResult(
            width=7680,
            height=2653,
            aspect_ratio=7680 / 2653,
            color_complexity=0.1,
            edge_density=0.01,
            alpha_present=False,
            route_type="wide_hires",
            should_tile=True,
            should_super_resolve=False,
        )
        result = enhance_image(config.input_path, analysis, config)
        self.assertEqual(result.image_path.name, "enhanced.png")
        self.assertTrue((output_dir / "enhance.json").exists())

    def test_enhance_image_accepts_unicode_input_path(self) -> None:
        output_dir = Path("outputs/test-enhance-unicode")
        self.addCleanup(shutil.rmtree, output_dir, ignore_errors=True)
        unicode_input = Path("picture/新建文件夹/d656b8bc-f179-4147-adc5-892858e4d8e7.png")

        config = PipelineConfig(input_path=unicode_input, output_dir=output_dir)
        analysis = AnalysisResult(
            width=111,
            height=149,
            aspect_ratio=111 / 149,
            color_complexity=0.1,
            edge_density=0.01,
            alpha_present=False,
            route_type="flat_graphics",
            should_tile=False,
            should_super_resolve=False,
        )

        result = enhance_image(config.input_path, analysis, config)

        self.assertEqual(result.image_path, output_dir / "enhanced.png")
        self.assertTrue(result.image_path.exists())


if __name__ == "__main__":
    unittest.main()
