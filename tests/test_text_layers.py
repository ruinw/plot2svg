from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from plot2svg.text_layers import separate_text_graphics, write_text_graphic_layers


class TextLayersTest(unittest.TestCase):
    def test_separate_text_graphics_reduces_text_signal_inside_text_bbox(self) -> None:
        image = np.full((160, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (220, 40), (290, 120), (0, 128, 255), -1)
        cv2.putText(image, 'HELLO', (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)

        layers = separate_text_graphics(image)

        original_text_patch = cv2.cvtColor(image[30:110, 10:220], cv2.COLOR_BGR2GRAY)
        graphic_text_patch = cv2.cvtColor(layers.graphic_layer[30:110, 10:220], cv2.COLOR_BGR2GRAY)
        original_shape_patch = image[40:120, 220:290]
        graphic_shape_patch = layers.graphic_layer[40:120, 220:290]

        self.assertGreater(int(np.count_nonzero(layers.text_mask)), 0)
        self.assertGreater(float(np.mean(graphic_text_patch)), float(np.mean(original_text_patch)))
        self.assertLess(float(np.mean(np.abs(graphic_shape_patch.astype(np.int16) - original_shape_patch.astype(np.int16)))), 12.0)

    def test_separate_text_graphics_does_not_cut_label_box_background(self) -> None:
        image = np.full((140, 260, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (60, 35), (210, 95), (223, 218, 191), -1)
        cv2.rectangle(image, (60, 35), (210, 95), (154, 144, 110), 2)
        cv2.putText(image, 'Phenotype', (78, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (35, 35, 35), 2, cv2.LINE_AA)

        layers = separate_text_graphics(image)

        # Sample the left/right interior strips of the label box away from most glyph strokes.
        original_left = image[45:85, 68:92]
        graphic_left = layers.graphic_layer[45:85, 68:92]
        original_right = image[45:85, 186:202]
        graphic_right = layers.graphic_layer[45:85, 186:202]

        self.assertLess(float(np.mean(np.abs(graphic_left.astype(np.int16) - original_left.astype(np.int16)))), 16.0)
        self.assertLess(float(np.mean(np.abs(graphic_right.astype(np.int16) - original_right.astype(np.int16)))), 16.0)

    def test_write_text_graphic_layers_persists_debug_files(self) -> None:
        image = np.full((64, 64, 3), 255, dtype=np.uint8)
        cv2.putText(image, 'A', (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2, cv2.LINE_AA)
        layers = separate_text_graphics(image)

        output_dir = Path(tempfile.gettempdir()) / 'plot2svg_text_layers_test'
        write_text_graphic_layers(output_dir, 'sample', layers)

        self.assertTrue((output_dir / 'sample_text_mask.png').exists())
        self.assertTrue((output_dir / 'sample_text_layer.png').exists())
        self.assertTrue((output_dir / 'sample_graphic_layer.png').exists())


if __name__ == '__main__':
    unittest.main()
