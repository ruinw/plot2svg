from pathlib import Path
import unittest

import cv2

from plot2svg.scene_graph import SceneNode
from plot2svg.vectorize_region import RegionVectorResult, vectorize_regions


class VectorizeRegionTest(unittest.TestCase):
    def test_region_vector_result_contains_svg_fragment(self) -> None:
        result = RegionVectorResult(component_id="r1", svg_fragment="<path />", path_count=1, simplified=False)
        self.assertIn("<path", result.svg_fragment)

    def test_vectorize_regions_only_processes_region_nodes(self) -> None:
        nodes = [
            SceneNode(id="region-1", type="region", bbox=[0, 0, 10, 10], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="stroke-1", type="stroke", bbox=[0, 0, 5, 5], z_index=2, vector_mode="stroke_path", confidence=0.8),
        ]
        results = vectorize_regions(Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"), nodes)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component_id, "region-1")

    def test_vectorize_regions_generates_nontrivial_path_from_image(self) -> None:
        nodes = [
            SceneNode(
                id="region-full",
                type="region",
                bbox=[0, 0, 1534, 704],
                z_index=1,
                vector_mode="region_path",
                confidence=0.95,
                fill="#ffffff",
                stroke="#000000",
            )
        ]
        results = vectorize_regions(Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"), nodes)
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0].path_count, 1)
        self.assertIn("L", results[0].svg_fragment)
        self.assertIn("fill=", results[0].svg_fragment)

    def test_vectorize_regions_accepts_loaded_image_array(self) -> None:
        image = cv2.imread("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png", cv2.IMREAD_COLOR)
        nodes = [
            SceneNode(id="region-full", type="region", bbox=[0, 0, 1534, 704], z_index=1, vector_mode="region_path", confidence=0.95, fill="#ffffff", stroke="#000000")
        ]
        results = vectorize_regions(image, nodes)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
