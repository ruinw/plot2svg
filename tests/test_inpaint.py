from pathlib import Path
import unittest

import numpy as np

from plot2svg.inpaint import _heal_masked_stage_image


class InpaintModuleTest(unittest.TestCase):
    def test_heal_masked_stage_image_closes_text_hole_without_inpainting(self) -> None:
        image = np.full((40, 40, 3), 255, dtype=np.uint8)
        image[8:32, 8:32] = (210, 235, 210)

        ignore_mask = np.zeros((40, 40), dtype=np.uint8)
        ignore_mask[17:23, 11:29] = 255

        healed = _heal_masked_stage_image(image, ignore_mask, kernel_size=7)

        self.assertTrue(np.array_equal(healed[19, 20], np.array([210, 235, 210], dtype=np.uint8)))
        self.assertTrue(np.array_equal(healed[4, 4], np.array([255, 255, 255], dtype=np.uint8)))


if __name__ == "__main__":
    unittest.main()
