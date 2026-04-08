"""Tests for geometric shape classification and SVG primitive generation."""

import math
import unittest

import cv2
import numpy as np

from plot2svg.detect_shapes import (
    SHAPE_CIRCLE,
    SHAPE_ELLIPSE,
    SHAPE_IRREGULAR,
    SHAPE_RECTANGLE,
    SHAPE_TRIANGLE,
    classify_contour,
    contour_to_svg_element,
    detect_circles_hough,
    svg_circle,
    svg_ellipse,
    svg_polygon,
    svg_rect,
)


def _make_circle_contour(cx: int = 100, cy: int = 100, r: int = 40, n: int = 64) -> np.ndarray:
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    pts = np.array([[cx + r * math.cos(a), cy + r * math.sin(a)] for a in angles], dtype=np.float32)
    return pts.reshape(-1, 1, 2).astype(np.int32)


def _make_ellipse_contour(cx: int = 150, cy: int = 150, rx: int = 60, ry: int = 35, n: int = 128) -> np.ndarray:
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    pts = np.array([[cx + rx * math.cos(a), cy + ry * math.sin(a)] for a in angles], dtype=np.float32)
    return pts.reshape(-1, 1, 2).astype(np.int32)


def _make_rect_contour(x: int = 20, y: int = 30, w: int = 80, h: int = 60) -> np.ndarray:
    pts = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.int32)
    return pts.reshape(-1, 1, 2)


def _make_triangle_contour() -> np.ndarray:
    pts = np.array([[100, 20], [40, 160], [160, 160]], dtype=np.int32)
    return pts.reshape(-1, 1, 2)


def _make_irregular_contour() -> np.ndarray:
    pts = np.array(
        [[10, 10], [50, 12], [55, 40], [30, 35], [20, 60], [5, 30]],
        dtype=np.int32,
    )
    return pts.reshape(-1, 1, 2)


class ClassifyContourTest(unittest.TestCase):
    def test_circle_contour_classified_as_circle(self) -> None:
        contour = _make_circle_contour()
        self.assertEqual(classify_contour(contour), SHAPE_CIRCLE)

    def test_ellipse_contour_classified_as_ellipse(self) -> None:
        contour = _make_ellipse_contour()
        self.assertEqual(classify_contour(contour), SHAPE_ELLIPSE)

    def test_rectangle_contour_classified_as_rectangle(self) -> None:
        contour = _make_rect_contour()
        self.assertEqual(classify_contour(contour), SHAPE_RECTANGLE)

    def test_triangle_contour_classified_as_triangle(self) -> None:
        contour = _make_triangle_contour()
        self.assertEqual(classify_contour(contour), SHAPE_TRIANGLE)

    def test_irregular_contour_fallback(self) -> None:
        contour = _make_irregular_contour()
        result = classify_contour(contour)
        self.assertIn(result, (SHAPE_IRREGULAR, "polygon"))


class SvgGeneratorTest(unittest.TestCase):
    def test_svg_circle_format(self) -> None:
        out = svg_circle("c1", 50.0, 60.0, 20.0, "none", "#000")
        self.assertIn("<circle", out)
        self.assertIn("cx='50.0'", out)
        self.assertIn("r='20.0'", out)

    def test_svg_ellipse_format(self) -> None:
        out = svg_ellipse("e1", 50.0, 60.0, 30.0, 15.0, 0.0, "none", "#000")
        self.assertIn("<ellipse", out)
        self.assertIn("rx='30.0'", out)
        self.assertNotIn("transform", out)

    def test_svg_ellipse_with_rotation(self) -> None:
        out = svg_ellipse("e2", 50.0, 60.0, 30.0, 15.0, 45.0, "none", "#000")
        self.assertIn("transform='rotate(45.0", out)

    def test_svg_rect_format(self) -> None:
        out = svg_rect("r1", 10.0, 20.0, 80.0, 60.0, "#fff", "#000")
        self.assertIn("<rect", out)
        self.assertIn("width='80.0'", out)

    def test_svg_polygon_format(self) -> None:
        pts = [(10.0, 20.0), (30.0, 20.0), (20.0, 40.0)]
        out = svg_polygon("p1", pts, "none", "#000")
        self.assertIn("<polygon", out)
        self.assertIn("points=", out)


class ContourToSvgTest(unittest.TestCase):
    def test_hint_circle_produces_circle_element(self) -> None:
        contour = _make_circle_contour()
        frag, shape = contour_to_svg_element(contour, "t1", 0, 0, "none", "#000", shape_hint="circle")
        self.assertIn("<circle", frag)
        self.assertEqual(shape, "circle")

    def test_auto_classify_circle(self) -> None:
        contour = _make_circle_contour()
        frag, shape = contour_to_svg_element(contour, "t2", 0, 0, "none", "#000")
        self.assertIn("<circle", frag)
        self.assertEqual(shape, "circle")

    def test_irregular_falls_back_to_path(self) -> None:
        contour = _make_irregular_contour()
        frag, shape = contour_to_svg_element(contour, "t3", 0, 0, "none", "#000", shape_hint="irregular")
        self.assertIn("<path", frag)
        self.assertEqual(shape, "irregular")


class HoughDetectionTest(unittest.TestCase):
    def test_hough_detects_synthetic_circles(self) -> None:
        img = np.zeros((200, 200), dtype=np.uint8)
        cv2.circle(img, (100, 100), 30, 255, 2)
        cv2.circle(img, (50, 50), 20, 255, 2)
        circles = detect_circles_hough(img, min_radius=10, max_radius=50)
        self.assertGreaterEqual(len(circles), 1)

    def test_hough_empty_image_returns_empty(self) -> None:
        img = np.zeros((100, 100), dtype=np.uint8)
        circles = detect_circles_hough(img)
        self.assertEqual(circles, [])


if __name__ == "__main__":
    unittest.main()
