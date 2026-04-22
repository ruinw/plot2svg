from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from plot2svg.config import PipelineConfig
from plot2svg.segment import ComponentProposal
from plot2svg.segmentation_backend import SamBackendUnavailableError, get_segmentation_backend


class SegmentationBackendTest(unittest.TestCase):
    def test_opencv_backend_delegates_to_existing_component_proposals(self) -> None:
        cfg = PipelineConfig(input_path=Path('picture/F2.png'), output_dir=Path('outputs/F2'))
        expected = [ComponentProposal('region-001', [0, 0, 10, 10], 'masks/r.png', 'region', 0.9)]
        image = np.full((12, 12, 3), 255, dtype=np.uint8)

        with patch('plot2svg.segmentation_backend.propose_components', return_value=expected) as propose:
            backend = get_segmentation_backend('opencv')
            proposals = backend.propose(image, Path('outputs/test-backend'), cfg=cfg)

        self.assertEqual(backend.name, 'opencv')
        self.assertEqual(proposals, expected)
        propose.assert_called_once()

    def test_sam_backend_raises_clear_unavailable_error(self) -> None:
        backend = get_segmentation_backend('sam_local')

        with self.assertRaises(SamBackendUnavailableError):
            backend.propose(np.full((4, 4, 3), 255, dtype=np.uint8), Path('outputs/test-sam'))

    def test_unknown_backend_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            get_segmentation_backend('unknown')


if __name__ == '__main__':
    unittest.main()