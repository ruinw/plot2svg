import unittest

import cv2
import numpy as np

from plot2svg.icon_processor import IconProcessor


class IconProcessorTest(unittest.TestCase):
    def test_evaluate_complexity_flags_multicolor_low_contour_icon(self) -> None:
        image = np.full((64, 64, 3), 255, dtype=np.uint8)
        cv2.circle(image, (32, 32), 18, (80, 170, 240), -1)
        cv2.circle(image, (32, 32), 11, (240, 220, 120), -1)
        cv2.line(image, (32, 32), (32, 18), (40, 40, 40), 2, cv2.LINE_AA)
        cv2.line(image, (32, 32), (42, 38), (40, 40, 40), 2, cv2.LINE_AA)

        processor = IconProcessor()
        complexity = processor.evaluate_complexity(image)

        self.assertTrue(complexity.is_complex)
        self.assertGreaterEqual(complexity.significant_colors, 3)

    def test_evaluate_complexity_flags_dark_curvy_black_fill_risk(self) -> None:
        image = np.full((72, 72, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (36, 40), (20, 14), 0, 20, 340, (0, 0, 0), 6)
        cv2.circle(image, (36, 22), 5, (0, 0, 0), -1)

        processor = IconProcessor()
        complexity = processor.evaluate_complexity(image)

        self.assertTrue(complexity.is_complex)
        self.assertTrue(getattr(complexity, 'black_fill_risk', False))

    def test_evaluate_complexity_flags_detail_rich_icon(self) -> None:
        image = np.full((40, 48, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (4, 4), (43, 35), (225, 240, 225), -1)
        cv2.circle(image, (12, 12), 4, (0, 0, 255), -1)
        cv2.rectangle(image, (20, 8), (30, 18), (255, 0, 0), -1)
        cv2.line(image, (8, 28), (36, 28), (0, 0, 0), 2, cv2.LINE_AA)

        processor = IconProcessor()
        complexity = processor.evaluate_complexity(image)

        self.assertTrue(complexity.is_complex)
        self.assertGreaterEqual(complexity.significant_colors, 2)
        self.assertGreaterEqual(complexity.contour_count, 1)
        self.assertTrue(processor.encode_image_href(image).startswith('data:image/png;base64,'))

    def test_evaluate_complexity_keeps_simple_solid_shape_vectorizable(self) -> None:
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (8, 8), (31, 31), (180, 220, 180), -1)

        processor = IconProcessor()
        complexity = processor.evaluate_complexity(image)

        self.assertFalse(complexity.is_complex)


if __name__ == '__main__':
    unittest.main()
