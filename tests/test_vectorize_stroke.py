from pathlib import Path
import unittest

import cv2

from plot2svg.scene_graph import SceneNode
from plot2svg.vectorize_stroke import StrokeVectorResult, vectorize_strokes


class VectorizeStrokeTest(unittest.TestCase):
    def test_stroke_vector_result_contains_bezier_commands(self) -> None:
        result = StrokeVectorResult(component_id="s1", svg_fragment="M 0 0 C 1 1 2 2 3 3", curve_count=1)
        self.assertTrue(result.svg_fragment.startswith("M "))

    def test_vectorize_strokes_only_processes_stroke_nodes(self) -> None:
        nodes = [
            SceneNode(id="region-1", type="region", bbox=[0, 0, 10, 10], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="stroke-1", type="stroke", bbox=[0, 0, 5, 5], z_index=2, vector_mode="stroke_path", confidence=0.8),
        ]
        results = vectorize_strokes(Path("picture/orr_signature.png"), nodes)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component_id, "stroke-1")

    def test_vectorize_strokes_generates_nontrivial_path_from_signature_image(self) -> None:
        nodes = [
            SceneNode(
                id="signature-stroke",
                type="stroke",
                bbox=[0, 0, 635, 568],
                z_index=1,
                vector_mode="stroke_path",
                confidence=0.95,
            )
        ]
        results = vectorize_strokes(Path("picture/orr_signature.png"), nodes)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].curve_count, 3)
        self.assertIn("L", results[0].svg_fragment)

    def test_vectorize_strokes_accepts_loaded_image_array(self) -> None:
        image = cv2.imread("picture/orr_signature.png", cv2.IMREAD_GRAYSCALE)
        nodes = [
            SceneNode(id="signature-stroke", type="stroke", bbox=[0, 0, 635, 568], z_index=1, vector_mode="stroke_path", confidence=0.95)
        ]
        results = vectorize_strokes(image, nodes)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
