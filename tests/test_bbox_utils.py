import unittest

from plot2svg.bbox_utils import _bbox_iou, _bbox_overlap, _clamp_bbox, _contains_bbox


class BboxUtilsTest(unittest.TestCase):
    def test_bbox_overlap_and_iou(self) -> None:
        left = [0, 0, 10, 10]
        right = [5, 5, 15, 15]

        self.assertAlmostEqual(_bbox_overlap(left, right), 0.25)
        self.assertAlmostEqual(_bbox_iou(left, right), 25 / 175)

    def test_contains_and_clamp_bbox(self) -> None:
        outer = [10, 10, 50, 50]
        inner = [18, 18, 42, 42]

        self.assertTrue(_contains_bbox(outer, inner, 0))
        self.assertEqual(_clamp_bbox([-10, -5, 120, 90], 100, 80), (0, 0, 100, 80))


if __name__ == "__main__":
    unittest.main()
