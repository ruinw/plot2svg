from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sandbox_icon_extractor import build_svg_path, select_root_indices, smooth_closed_polygon, write_svg


def make_icon_like_mask() -> np.ndarray:
    mask = np.zeros((160, 160), dtype=np.uint8)
    cv2.rectangle(mask, (20, 10), (120, 90), 255, thickness=-1)
    cv2.rectangle(mask, (42, 28), (98, 72), 0, thickness=-1)
    cv2.rectangle(mask, (8, 128), (48, 142), 255, thickness=-1)
    cv2.rectangle(mask, (64, 128), (102, 142), 255, thickness=-1)
    return mask


class SandboxIconExtractorTest(unittest.TestCase):
    def test_select_root_indices_prefers_dominant_icon_root(self) -> None:
        mask = make_icon_like_mask()
        contours, raw_hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        hierarchy = raw_hierarchy[0]

        roots = select_root_indices(contours, hierarchy, mask.shape)

        self.assertEqual(len(roots), 1)
        x, y, w, h = cv2.boundingRect(contours[roots[0]])
        self.assertLessEqual(y, 12)
        self.assertGreaterEqual(h, 78)

    def test_build_svg_path_keeps_outer_and_hole_paths(self) -> None:
        mask = make_icon_like_mask()
        contours, raw_hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        hierarchy = raw_hierarchy[0]

        roots = select_root_indices(contours, hierarchy, mask.shape)
        compound_path, nodes = build_svg_path(contours, hierarchy, roots)

        self.assertGreaterEqual(len(nodes), 2)
        self.assertGreaterEqual(compound_path.count("M "), 2)

    def test_write_svg_uses_evenodd_fill(self) -> None:
        tmp_dir = Path(tempfile.gettempdir())
        out_path = tmp_dir / "sandbox_icon_extractor_test.svg"

        write_svg(out_path, 20, 20, "M 1,1 L 10,1 L 10,10 Z M 3,3 L 6,3 L 6,6 Z")

        svg = out_path.read_text(encoding="utf-8")
        self.assertIn("fill-rule='evenodd'", svg)

    def test_smooth_closed_polygon_removes_short_zigzag_vertices(self) -> None:
        points = np.asarray(
            [
                [0, 0],
                [8, 0],
                [9, 1],
                [10, 0],
                [18, 0],
                [18, 12],
                [0, 12],
            ],
            dtype=np.int32,
        )

        smoothed = smooth_closed_polygon(points)

        self.assertLess(len(smoothed), len(points))
        self.assertGreaterEqual(len(smoothed), 4)


if __name__ == "__main__":
    unittest.main()
