import unittest

import cv2
import numpy as np

from plot2svg.panel_detection import _detect_panel_arrow_regions, _inject_panel_background_regions
from plot2svg.scene_graph import SceneGraph, SceneNode


class PanelDetectionTest(unittest.TestCase):
    def test_inject_panel_background_regions_adds_layout_panels_from_text_columns(self) -> None:
        image = np.full((220, 400, 3), 255, dtype=np.uint8)
        colors = [(240, 240, 224), (232, 216, 232), (208, 224, 240), (216, 224, 216)]
        bounds = [(0, 98), (100, 198), (200, 298), (300, 399)]
        for (x1, x2), color in zip(bounds, colors):
            cv2.rectangle(image, (x1, 12), (x2, 208), color, -1)

        scene_graph = SceneGraph(
            width=400,
            height=220,
            nodes=[SceneNode(id='background-root', type='background', bbox=[0, 0, 400, 220], z_index=0, vector_mode='region_path', confidence=1.0)],
        )
        text_nodes = [
            SceneNode(id='text-1', type='text', bbox=[20, 24, 80, 46], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Panel 1'),
            SceneNode(id='text-2', type='text', bbox=[120, 24, 180, 46], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Panel 2'),
            SceneNode(id='text-3', type='text', bbox=[220, 24, 280, 46], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Panel 3'),
            SceneNode(id='text-4', type='text', bbox=[320, 24, 380, 46], z_index=4, vector_mode='text_box', confidence=0.9, text_content='Panel 4'),
        ]

        updated = _inject_panel_background_regions(image, scene_graph, text_nodes)

        panel_nodes = [node for node in updated.nodes if node.id.startswith('panel-region-')]
        self.assertEqual(len(panel_nodes), 4)
        self.assertTrue(all(node.shape_hint == 'panel' for node in panel_nodes))

    def test_detect_panel_arrow_regions_uses_arrow_fill_and_marks_panel_arrow(self) -> None:
        image = np.full((320, 420, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (180, 280), (240, 240, 224), -1)
        cv2.rectangle(image, (220, 20), (400, 280), (232, 216, 232), -1)
        arrow_color = (128, 48, 112)
        arrow_points = np.array([[150, 150], [220, 150], [255, 170], [220, 190], [150, 190]], dtype=np.int32)
        cv2.fillConvexPoly(image, arrow_points, arrow_color)

        panel_nodes = [
            SceneNode(id='panel-region-000', type='region', bbox=[20, 20, 180, 280], z_index=1, vector_mode='region_path', confidence=0.99, fill='#e0f0f0', shape_hint='panel'),
            SceneNode(id='panel-region-001', type='region', bbox=[220, 20, 400, 280], z_index=2, vector_mode='region_path', confidence=0.99, fill='#f0e0f0', shape_hint='panel'),
        ]

        arrow_nodes, arrow_objects = _detect_panel_arrow_regions(image, image.copy(), panel_nodes)

        self.assertTrue(arrow_nodes)
        self.assertTrue(arrow_objects)
        self.assertTrue(all(node.shape_hint == 'panel_arrow' for node in arrow_nodes))
        self.assertTrue(all(obj.metadata.get('shape_type') == 'panel_arrow_template' for obj in arrow_objects))


if __name__ == "__main__":
    unittest.main()
