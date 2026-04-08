from pathlib import Path
import unittest

import numpy as np

from plot2svg.image_io import read_image, write_image


class ImageIoTest(unittest.TestCase):
    def test_read_image_accepts_unicode_path(self) -> None:
        unicode_input = Path("picture/新建文件夹/d656b8bc-f179-4147-adc5-892858e4d8e7.png")

        image = read_image(unicode_input)

        self.assertIsNotNone(image)
        self.assertGreater(image.shape[0], 0)
        self.assertGreater(image.shape[1], 0)

    def test_write_image_preserves_unicode_path(self) -> None:
        unicode_output = Path("outputs/测试写出.png")
        if unicode_output.exists():
            unicode_output.unlink()
        self.addCleanup(lambda: unicode_output.unlink() if unicode_output.exists() else None)

        written = write_image(unicode_output, np.zeros((8, 8, 3), dtype=np.uint8))

        self.assertTrue(written)
        self.assertTrue(unicode_output.exists())


if __name__ == "__main__":
    unittest.main()
