from pathlib import Path
import re
import unittest

import cv2
import numpy as np

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

    def test_vectorize_regions_supports_scaled_coordinate_space(self) -> None:
        image = cv2.imread("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png", cv2.IMREAD_COLOR)
        upscaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        nodes = [
            SceneNode(id="region-full", type="region", bbox=[0, 0, 1534, 704], z_index=1, vector_mode="region_path", confidence=0.95, fill="#ffffff", stroke="#000000")
        ]
        results = vectorize_regions(upscaled, nodes, coordinate_scale=2.0)
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0].path_count, 1)

    def test_circle_hint_produces_circle_svg_element(self) -> None:
        image = cv2.imread("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png", cv2.IMREAD_COLOR)
        nodes = [
            SceneNode(
                id="region-circle",
                type="region",
                bbox=[0, 0, 100, 100],
                z_index=1,
                vector_mode="region_path",
                confidence=0.9,
                fill="#ffffff",
                stroke="#000000",
                shape_hint="circle",
            )
        ]
        results = vectorize_regions(image, nodes)
        self.assertEqual(len(results), 1)
        self.assertIn("<circle", results[0].svg_fragment)

    def test_simple_filled_circle_region_prefers_circle_element(self) -> None:
        image = np.full((140, 140, 3), 255, dtype=np.uint8)
        cv2.circle(image, (70, 70), 42, (208, 176, 192), -1)
        nodes = [
            SceneNode(
                id="region-filled-circle",
                type="region",
                bbox=[20, 20, 120, 120],
                z_index=1,
                vector_mode="region_path",
                confidence=0.95,
                fill="#c0b0d0",
                stroke="#c0b0d0",
                fill_opacity=0.55,
            )
        ]

        results = vectorize_regions(image, nodes)

        self.assertEqual(len(results), 1)
        self.assertIn("<circle", results[0].svg_fragment)
        self.assertNotIn("<path", results[0].svg_fragment)

    def test_simple_filled_ellipse_region_prefers_ellipse_element(self) -> None:
        image = np.full((160, 180, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (90, 80), (58, 34), 18, 0, 360, (208, 176, 192), -1)
        nodes = [
            SceneNode(
                id="region-filled-ellipse",
                type="region",
                bbox=[20, 20, 160, 140],
                z_index=1,
                vector_mode="region_path",
                confidence=0.95,
                fill="#c0b0d0",
                stroke="#c0b0d0",
                fill_opacity=0.55,
            )
        ]

        results = vectorize_regions(image, nodes)

        self.assertEqual(len(results), 1)
        self.assertIn("<ellipse", results[0].svg_fragment)
        self.assertNotIn("<path", results[0].svg_fragment)


    def test_black_icon_region_ignores_small_detached_roots_and_keeps_evenodd(self) -> None:
        image = np.full((200, 140, 3), 255, dtype=np.uint8)
        fill_bgr = (17, 17, 17)
        cv2.rectangle(image, (20, 10), (120, 90), fill_bgr, -1)
        cv2.rectangle(image, (42, 28), (98, 72), (255, 255, 255), -1)
        cv2.rectangle(image, (8, 160), (48, 176), fill_bgr, -1)
        cv2.rectangle(image, (64, 160), (104, 176), fill_bgr, -1)

        nodes = [
            SceneNode(
                id="region-icon",
                type="region",
                bbox=[0, 0, 140, 200],
                z_index=1,
                vector_mode="region_path",
                confidence=0.95,
                fill="#111111",
                stroke="#111111",
            )
        ]

        results = vectorize_regions(image, nodes)

        self.assertEqual(len(results), 1)
        self.assertIn("fill-rule='evenodd'", results[0].svg_fragment)
        path_match = re.search(r"d='([^']+)'", results[0].svg_fragment)
        self.assertIsNotNone(path_match)
        values = [float(token) for token in re.findall(r"-?\d+(?:\.\d+)?", path_match.group(1))]
        self.assertTrue(values)
        self.assertLess(max(values), 150.0)

    def test_complex_filled_region_with_holes_keeps_path_instead_of_circle(self) -> None:
        image = np.full((140, 140, 3), 255, dtype=np.uint8)
        fill_bgr = (208, 176, 192)
        cv2.circle(image, (70, 70), 42, fill_bgr, -1)
        cv2.circle(image, (54, 56), 10, (255, 255, 255), -1)
        cv2.circle(image, (86, 60), 8, (255, 255, 255), -1)
        cv2.circle(image, (72, 88), 9, (255, 255, 255), -1)

        nodes = [
            SceneNode(
                id="region-holey",
                type="region",
                bbox=[20, 20, 120, 120],
                z_index=1,
                vector_mode="region_path",
                confidence=0.95,
                fill="#c0b0d0",
                stroke="#c0b0d0",
                fill_opacity=0.55,
            )
        ]

        results = vectorize_regions(image, nodes)
        self.assertEqual(len(results), 1)
        self.assertIn("<path", results[0].svg_fragment)
        self.assertIn("fill-rule='evenodd'", results[0].svg_fragment)
        self.assertNotIn("<circle", results[0].svg_fragment)


if __name__ == "__main__":
    unittest.main()
