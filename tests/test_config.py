from pathlib import Path
import unittest

from plot2svg.config import PipelineConfig, ThresholdConfig


class PipelineConfigTest(unittest.TestCase):
    def test_pipeline_config_resolves_output_dir(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(config.output_dir, Path("outputs/F2"))

    def test_pipeline_config_defaults_to_auto_enhancement(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(config.enhancement_mode, "auto")

    def test_pipeline_config_defaults_to_balanced_profile(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(config.execution_profile, "balanced")

    def test_pipeline_config_rejects_invalid_profile(self) -> None:
        with self.assertRaises(ValueError):
            PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="turbo")

    def test_execution_profiles_change_processing_policy(self) -> None:
        speed = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="speed")
        quality = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="quality")
        self.assertLess(speed.proposal_max_side(), quality.proposal_max_side())
        self.assertGreater(speed.text_skip_min_width(), quality.text_skip_min_width())
        self.assertLess(speed.ocr_variant_count(), quality.ocr_variant_count())

    def test_pipeline_config_exposes_threshold_config(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))

        self.assertIsInstance(config.thresholds, ThresholdConfig)
        self.assertEqual(config.thresholds.graph_monster_stroke_width, 15.0)


if __name__ == "__main__":
    unittest.main()
