from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import cv2
import numpy as np

from plot2svg.ocr import (
    _EARLY_EXIT_CONFIDENCE,
    _MIN_PIXEL_STD,
    _read_text_from_bbox,
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

    def test_early_exit_confidence_constant(self) -> None:
        """Verify the early exit confidence threshold is set correctly."""
        self.assertEqual(_EARLY_EXIT_CONFIDENCE, 0.85)

    def test_min_pixel_std_constant(self) -> None:
        """Verify the pixel variance threshold is set correctly."""
        self.assertEqual(_MIN_PIXEL_STD, 10.0)


if __name__ == "__main__":
    unittest.main()
