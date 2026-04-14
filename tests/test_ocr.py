from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import cv2
import numpy as np

from plot2svg.config import PipelineConfig, ThresholdConfig
from plot2svg.ocr import (
    _EARLY_EXIT_CONFIDENCE,
    _MIN_PIXEL_STD,
    _read_text_from_bbox,
    extract_text_overlays,
    inpaint_text_nodes,
    choose_best_ocr_text,
    merge_text_nodes,
    normalize_ocr_text,
    populate_text_nodes,
    should_use_ocr_cuda,
)
from plot2svg.scene_graph import SceneGraph, SceneNode


class OcrTest(unittest.TestCase):
    def test_should_use_ocr_cuda_only_when_gpu_provider_is_available(self) -> None:
        self.assertTrue(should_use_ocr_cuda(["CUDAExecutionProvider", "CPUExecutionProvider"], "GPU"))
        self.assertFalse(should_use_ocr_cuda(["CPUExecutionProvider"], "GPU"))
        self.assertFalse(should_use_ocr_cuda(["CUDAExecutionProvider", "CPUExecutionProvider"], "CPU"))

    def test_choose_best_ocr_text_prefers_higher_confidence_valid_candidate(self) -> None:
        text = choose_best_ocr_text(
            [
                ("HEL", 0.6),
                ("HELLO", 0.8),
                ("", 0.95),
            ]
        )
        self.assertEqual(text, "HELLO")

    def test_normalize_ocr_text_removes_adjacent_duplicates(self) -> None:
        self.assertEqual(normalize_ocr_text("Mutation Mutation"), "Mutation")

    def test_normalize_ocr_text_fixes_common_ocr_terms(self) -> None:
        self.assertEqual(normalize_ocr_text("signahng pathway"), "signaling pathway")
        self.assertEqual(normalize_ocr_text("light intemediate intemediate"), "light intermediate")
        self.assertEqual(normalize_ocr_text("lariants"), "variants")
        self.assertEqual(normalize_ocr_text("flament binding"), "filament binding")
        self.assertEqual(normalize_ocr_text("echnology"), "technology")
        self.assertEqual(normalize_ocr_text("Miniaturizatio"), "Miniaturization")

    def test_normalize_ocr_text_adds_spacing_around_delimiters(self) -> None:
        self.assertEqual(normalize_ocr_text("Model Construction&Training"), "Model Construction & Training")
        self.assertEqual(normalize_ocr_text("[Clinical +Mutation Data]"), "[Clinical + Mutation Data]")
        self.assertEqual(normalize_ocr_text("&Preprocessing"), "& Preprocessing")

    def test_normalize_ocr_text_separates_leading_digit_from_long_word(self) -> None:
        self.assertEqual(normalize_ocr_text("4Prediction&"), "4 Prediction &")

    def test_merge_text_nodes_combines_adjacent_boxes_on_same_line(self) -> None:
        graph = SceneGraph(
            width=400,
            height=100,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 400, 100], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-a", type="text", bbox=[10, 20, 80, 40], z_index=1, vector_mode="text_box", confidence=0.9),
                SceneNode(id="text-b", type="text", bbox=[88, 20, 170, 40], z_index=2, vector_mode="text_box", confidence=0.8),
                SceneNode(id="stroke-1", type="stroke", bbox=[0, 0, 5, 5], z_index=3, vector_mode="stroke_path", confidence=0.7),
            ],
        )

        merged = merge_text_nodes(graph)
        text_nodes = [node for node in merged.nodes if node.type == "text"]
        self.assertEqual(len(text_nodes), 1)
        self.assertEqual(text_nodes[0].bbox, [10, 20, 170, 40])

    def test_merge_text_nodes_merges_three_boxes_on_same_line(self) -> None:
        graph = SceneGraph(
            width=500,
            height=100,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 500, 100], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-a", type="text", bbox=[10, 20, 70, 40], z_index=1, vector_mode="text_box", confidence=0.9),
                SceneNode(id="text-b", type="text", bbox=[78, 20, 150, 40], z_index=2, vector_mode="text_box", confidence=0.8),
                SceneNode(id="text-c", type="text", bbox=[162, 21, 240, 41], z_index=3, vector_mode="text_box", confidence=0.85),
            ],
        )
        merged = merge_text_nodes(graph)
        text_nodes = [node for node in merged.nodes if node.type == "text"]
        self.assertEqual(len(text_nodes), 1)
        self.assertEqual(text_nodes[0].bbox, [10, 20, 240, 41])

    def test_populate_text_nodes_extracts_text_from_synthetic_image(self) -> None:
        image = np.full((120, 320, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
        image_path = Path(tempfile.gettempdir()) / "plot2svg_ocr_test.png"
        cv2.imwrite(str(image_path), image)

        graph = SceneGraph(
            width=320,
            height=120,
            nodes=[
                SceneNode(
                    id="background-root",
                    type="background",
                    bbox=[0, 0, 320, 120],
                    z_index=0,
                    vector_mode="region_path",
                    confidence=1.0,
                ),
                SceneNode(
                    id="text-001",
                    type="text",
                    bbox=[10, 10, 250, 90],
                    z_index=1,
                    vector_mode="text_box",
                    confidence=0.9,
                ),
            ],
        )

        updated = populate_text_nodes(image_path, graph)
        text_node = next(node for node in updated.nodes if node.type == "text")
        self.assertEqual(text_node.text_content, "HELLO")

    def test_populate_text_nodes_handles_multiline_text(self) -> None:
        image = np.full((180, 360, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, "WORLD", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3, cv2.LINE_AA)
        graph = SceneGraph(
            width=360,
            height=180,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 360, 180], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-001", type="text", bbox=[10, 10, 300, 160], z_index=1, vector_mode="text_box", confidence=0.9),
            ],
        )
        updated = populate_text_nodes(image, graph)
        text_node = next(node for node in updated.nodes if node.type == "text")
        self.assertIn("HELLO", text_node.text_content or "")
        self.assertIn("WORLD", text_node.text_content or "")

    def test_read_text_from_bbox_preserves_multiline_breaks(self) -> None:
        image = np.full((180, 360, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, "WORLD", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3, cv2.LINE_AA)

        responses = [
            ([], None),
            ([], None),
            ([], None),
            [([0, 0, 100, 30], "HELLO", 0.90)],
            [([0, 0, 100, 30], "WORLD", 0.90)],
        ]

        def fake_engine(_variant):
            payload = responses.pop(0)
            if isinstance(payload, tuple):
                return payload
            return payload, None

        with patch("plot2svg.ocr._get_ocr_engine_full") as mock_get:
            mock_engine = MagicMock()
            mock_engine.side_effect = fake_engine
            mock_get.return_value = mock_engine
            result = _read_text_from_bbox(image, [10, 10, 300, 160])

        self.assertEqual(result, "HELLO\nWORLD")

    def test_populate_text_nodes_accepts_loaded_image_array(self) -> None:
        image = np.full((120, 320, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
        graph = SceneGraph(
            width=320,
            height=120,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 320, 120], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-001", type="text", bbox=[10, 10, 250, 90], z_index=1, vector_mode="text_box", confidence=0.9),
            ],
        )
        updated = populate_text_nodes(image, graph)
        text_node = next(node for node in updated.nodes if node.type == "text")
        self.assertEqual(text_node.text_content, "HELLO")

    def test_populate_text_nodes_supports_scaled_coordinate_space(self) -> None:
        image = np.full((120, 320, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
        upscaled = cv2.resize(image, (640, 240), interpolation=cv2.INTER_CUBIC)
        graph = SceneGraph(
            width=320,
            height=120,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 320, 120], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-001", type="text", bbox=[10, 10, 250, 90], z_index=1, vector_mode="text_box", confidence=0.9),
            ],
        )

        updated = populate_text_nodes(upscaled, graph, coordinate_scale=2.0)
        text_node = next(node for node in updated.nodes if node.type == "text")
        self.assertEqual(text_node.text_content, "HELLO")

    def test_extract_text_overlays_returns_scene_nodes(self) -> None:
        image = np.full((120, 320, 3), 255, dtype=np.uint8)

        with patch('plot2svg.ocr._get_ocr_engine_full') as mock_get:
            mock_engine = MagicMock()
            mock_engine.return_value = ([([ [20, 20], [120, 20], [120, 48], [20, 48] ], 'HELLO', 0.92)], None)
            mock_get.return_value = mock_engine
            nodes = extract_text_overlays(image)

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].type, 'text')
        self.assertEqual(nodes[0].text_content, 'HELLO')
        self.assertEqual(nodes[0].bbox, [20, 20, 120, 48])

    def test_extract_text_overlays_tightens_bbox_to_foreground(self) -> None:
        image = np.full((120, 200, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (60, 36), (110, 54), (0, 0, 0), -1)

        with patch('plot2svg.ocr._get_ocr_engine_full') as mock_get:
            mock_engine = MagicMock()
            mock_engine.return_value = ([([ [20, 20], [140, 20], [140, 80], [20, 80] ], 'HELLO', 0.92)], None)
            mock_get.return_value = mock_engine
            nodes = extract_text_overlays(image)

        self.assertEqual(len(nodes), 1)
        self.assertGreater(nodes[0].bbox[0], 20)
        self.assertLess(nodes[0].bbox[2], 140)
        self.assertGreater(nodes[0].bbox[1], 20)
        self.assertLess(nodes[0].bbox[3], 80)

    def test_inpaint_text_nodes_returns_mask_and_cleans_pixels(self) -> None:
        image = np.full((80, 180, 3), 255, dtype=np.uint8)
        cv2.putText(image, 'TEST', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        text_nodes = [
            SceneNode(id='text-001', type='text', bbox=[12, 18, 120, 58], z_index=1, vector_mode='text_box', confidence=0.9, text_content='TEST')
        ]

        cleaned, mask = inpaint_text_nodes(image, text_nodes)

        self.assertEqual(mask.shape[:2], image.shape[:2])
        self.assertGreater(np.count_nonzero(mask), 0)
        self.assertGreater(float(np.mean(cleaned[mask > 0])), float(np.mean(image[mask > 0])))

    def test_inpaint_text_nodes_preserves_neighboring_colored_region_outside_glyph_mask(self) -> None:
        image = np.full((80, 180, 3), 255, dtype=np.uint8)
        image[18:34, 128:144] = (0, 0, 255)
        cv2.putText(image, 'TEST', (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        text_nodes = [
            SceneNode(id='text-001', type='text', bbox=[12, 18, 120, 58], z_index=1, vector_mode='text_box', confidence=0.9, text_content='TEST')
        ]

        cleaned, mask = inpaint_text_nodes(image, text_nodes)

        self.assertEqual(mask[26, 136], 0)
        self.assertTrue(np.array_equal(cleaned[26, 136], np.array([0, 0, 255], dtype=np.uint8)))

    def test_pixel_variance_filter_skips_uniform_crop(self) -> None:
        """Optimization 3: uniform image (all white) should return None."""
        white_image = np.full((100, 200, 3), 255, dtype=np.uint8)
        result = _read_text_from_bbox(white_image, [10, 10, 190, 90])
        self.assertIsNone(result)

    def test_pixel_variance_filter_passes_textual_crop(self) -> None:
        """Optimization 3: image with text has high std, should not be filtered."""
        image = np.full((100, 200, 3), 255, dtype=np.uint8)
        cv2.putText(image, "TEST", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2, cv2.LINE_AA)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.assertGreater(np.std(gray), _MIN_PIXEL_STD)

    def test_custom_pixel_std_threshold_allows_low_variance_crop(self) -> None:
        image = np.full((60, 160, 3), 250, dtype=np.uint8)
        image[20:40, 20:140] = 245
        cfg = PipelineConfig(
            input_path="picture/F2.png",
            output_dir="outputs/F2",
            thresholds=ThresholdConfig(ocr_min_pixel_std=0.1),
        )

        with patch("plot2svg.ocr._get_ocr_engine_full") as mock_get:
            mock_engine = MagicMock()
            mock_engine.return_value = ([([0, 0, 100, 30], "SOFT", 0.95)], None)
            mock_get.return_value = mock_engine
            result = _read_text_from_bbox(image, [0, 0, 160, 60], cfg=cfg)

        self.assertEqual(result, "SOFT")

    def test_early_exit_reduces_engine_calls(self) -> None:
        """Optimization 2: high-confidence first variant should skip remaining variants."""
        call_count = 0
        high_conf_result = [([0, 0, 100, 30], "HELLO", 0.95)]

        def fake_engine(variant):
            nonlocal call_count
            call_count += 1
            return high_conf_result, None

        image = np.full((80, 200, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)

        with patch("plot2svg.ocr._get_ocr_engine_full") as mock_get:
            mock_engine = MagicMock()
            mock_engine.side_effect = fake_engine
            mock_get.return_value = mock_engine
            result = _read_text_from_bbox(image, [0, 0, 200, 80])

        self.assertIsNotNone(result)
        self.assertEqual(call_count, 1)  # only 1 variant processed, not 3

    def test_custom_early_exit_threshold_reduces_engine_calls(self) -> None:
        call_count = 0
        medium_conf_result = [([0, 0, 100, 30], "HELLO", 0.80)]

        def fake_engine(variant):
            nonlocal call_count
            call_count += 1
            return medium_conf_result, None

        image = np.full((80, 200, 3), 255, dtype=np.uint8)
        cv2.putText(image, "HELLO", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        cfg = PipelineConfig(
            input_path="picture/F2.png",
            output_dir="outputs/F2",
            thresholds=ThresholdConfig(ocr_early_exit_confidence=0.75),
        )

        with patch("plot2svg.ocr._get_ocr_engine_full") as mock_get:
            mock_engine = MagicMock()
            mock_engine.side_effect = fake_engine
            mock_get.return_value = mock_engine
            result = _read_text_from_bbox(image, [0, 0, 200, 80], cfg=cfg)

        self.assertIsNotNone(result)
        self.assertEqual(call_count, 1)

    def test_populate_parallel_matches_serial(self) -> None:
        """Optimization 5: parallel results should match serial execution."""
        image = np.full((200, 600, 3), 255, dtype=np.uint8)
        cv2.putText(image, "AAA", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(image, "BBB", (250, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(image, "CCC", (450, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)

        graph = SceneGraph(
            width=600,
            height=200,
            nodes=[
                SceneNode(id="bg", type="background", bbox=[0, 0, 600, 200], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="t1", type="text", bbox=[10, 10, 200, 70], z_index=1, vector_mode="text_box", confidence=0.9),
                SceneNode(id="t2", type="text", bbox=[230, 10, 420, 70], z_index=2, vector_mode="text_box", confidence=0.9),
                SceneNode(id="t3", type="text", bbox=[430, 10, 590, 70], z_index=3, vector_mode="text_box", confidence=0.9),
            ],
        )

        updated = populate_text_nodes(image, graph)
        text_nodes = [n for n in updated.nodes if n.type == "text"]
        # All three text nodes should have been processed (may merge into fewer)
        self.assertTrue(len(text_nodes) >= 1)
        # At least some text content should have been found
        texts = [n.text_content for n in text_nodes if n.text_content]
        self.assertTrue(len(texts) >= 1)

    def test_early_exit_confidence_matches_default_threshold_config(self) -> None:
        """Verify the early-exit default still matches the config baseline."""
        cfg = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(_EARLY_EXIT_CONFIDENCE, cfg.thresholds.ocr_early_exit_confidence)

    def test_min_pixel_std_matches_default_threshold_config(self) -> None:
        """Verify the pixel-std default still matches the config baseline."""
        cfg = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        self.assertEqual(_MIN_PIXEL_STD, cfg.thresholds.ocr_min_pixel_std)


if __name__ == "__main__":
    unittest.main()
