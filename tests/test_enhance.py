from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
