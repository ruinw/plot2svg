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
        self.assertEqual(config.thresholds.detect_shapes_circle_circularity, 0.82)
        self.assertEqual(config.thresholds.detect_shapes_rect_fill_min, 0.88)
        self.assertEqual(config.thresholds.stroke_sane_canvas_span_ratio, 0.8)
        self.assertEqual(config.thresholds.stroke_min_polyline_length, 15.0)
        self.assertEqual(config.thresholds.detect_structure_box_aspect_max, 6.0)
        self.assertEqual(config.thresholds.detect_structure_fan_min_source_count, 4)
        self.assertEqual(config.thresholds.graph_route_grid_size_default, 8)
        self.assertEqual(config.thresholds.graph_obstacle_text_padding, 20)
        self.assertEqual(config.thresholds.graph_partial_repair_min_length, 60.0)
        self.assertEqual(config.thresholds.graph_direct_snap_node_min, 24.0)
        self.assertEqual(config.thresholds.ocr_early_exit_confidence, 0.85)
        self.assertEqual(config.thresholds.ocr_min_pixel_std, 10.0)
        self.assertEqual(config.thresholds.segment_text_like_max_height, 28)
        self.assertEqual(config.thresholds.segment_min_area_region_abs, 96)
        self.assertEqual(config.thresholds.analyze_route_wide_min_width, 3000)
        self.assertEqual(config.thresholds.analyze_signature_dark_ratio_max, 0.18)



    def test_pipeline_config_defaults_to_opencv_segmentation_and_template_output(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(config.segmentation_backend, "opencv")
        self.assertTrue(config.emit_layout_template)
        self.assertEqual(config.template_optimization, "deterministic")


    def test_pipeline_config_accepts_future_sam_backend_names(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), segmentation_backend="sam_local")
        self.assertEqual(config.segmentation_backend, "sam_local")
    def test_pipeline_config_rejects_unsupported_segmentation_backend(self) -> None:
        with self.assertRaises(ValueError):
            PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), segmentation_backend="unknown")

    def test_pipeline_config_rejects_unsupported_template_optimization(self) -> None:
        with self.assertRaises(ValueError):
            PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), template_optimization="magic")

if __name__ == "__main__":
    unittest.main()
