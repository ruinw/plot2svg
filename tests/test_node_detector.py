from pathlib import Path
import unittest

import cv2
import numpy as np

from plot2svg.node_detector import detect_nodes
from plot2svg.scene_graph import SceneGraph, SceneNode


class NodeDetectorTest(unittest.TestCase):
    def test_detect_nodes_promotes_triangle_and_pentagon_with_shape_metadata(self) -> None:
        image = np.full((220, 260, 3), 255, dtype=np.uint8)

        triangle = np.array([[50, 120], [90, 50], [130, 120]], dtype=np.int32)
        pentagon = np.array([[170, 120], [195, 70], [235, 88], [228, 132], [182, 142]], dtype=np.int32)
        cv2.fillPoly(image, [triangle], (0, 0, 0))
        cv2.fillPoly(image, [pentagon], (0, 0, 0))

        graph = SceneGraph(
            width=260,
            height=220,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 260, 220], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='triangle-region', type='region', bbox=[46, 46, 134, 126], z_index=1, vector_mode='region_path', confidence=0.9),
                SceneNode(id='pentagon-region', type='region', bbox=[166, 66, 238, 146], z_index=2, vector_mode='region_path', confidence=0.9),
            ],
        )

        nodes = detect_nodes(image, graph)

        self.assertEqual(len(nodes), 2)
        metadata_by_node = {node.node_id: node.metadata for node in nodes}
        self.assertEqual(metadata_by_node['triangle-region']['shape_type'], 'triangle')
        self.assertEqual(metadata_by_node['triangle-region']['vertex_count'], 3)
        self.assertEqual(metadata_by_node['pentagon-region']['shape_type'], 'pentagon')
        self.assertEqual(metadata_by_node['pentagon-region']['vertex_count'], 5)

    def test_detect_nodes_suppresses_near_duplicate_circle_nodes(self) -> None:
        image = np.full((180, 180, 3), 255, dtype=np.uint8)
        cv2.circle(image, (90, 90), 34, (0, 0, 0), -1)

        graph = SceneGraph(
            width=180,
            height=180,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 180, 180], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-001', type='region', bbox=[52, 52, 128, 128], z_index=1, vector_mode='region_path', confidence=0.95, shape_hint='circle'),
                SceneNode(id='region-hough-001', type='region', bbox=[55, 55, 125, 125], z_index=2, vector_mode='region_path', confidence=0.75, shape_hint='circle'),
            ],
        )

        nodes = detect_nodes(image, graph)

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_id, 'region-001')

    def test_detect_nodes_suppresses_small_hough_circle_inside_large_circle(self) -> None:
        image = np.full((220, 220, 3), 255, dtype=np.uint8)
        cv2.circle(image, (110, 110), 58, (0, 0, 0), -1)
        cv2.circle(image, (145, 110), 10, (255, 255, 255), -1)

        graph = SceneGraph(
            width=220,
            height=220,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 220, 220], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-001', type='region', bbox=[48, 48, 172, 172], z_index=1, vector_mode='region_path', confidence=0.95, shape_hint='circle'),
                SceneNode(id='region-hough-001', type='region', bbox=[136, 100, 156, 120], z_index=2, vector_mode='region_path', confidence=0.7, shape_hint='circle'),
            ],
        )

        nodes = detect_nodes(image, graph)

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].node_id, 'region-001')

    def test_detect_nodes_records_triangle_orientation_metadata(self) -> None:
        image = np.full((220, 220, 3), 255, dtype=np.uint8)
        triangle = np.array([[110, 40], [55, 150], [165, 150]], dtype=np.int32)
        cv2.fillPoly(image, [triangle], (0, 0, 0))

        graph = SceneGraph(
            width=220,
            height=220,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 220, 220], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='triangle-region', type='region', bbox=[50, 35, 170, 155], z_index=1, vector_mode='region_path', confidence=0.95, shape_hint='triangle'),
            ],
        )

        nodes = detect_nodes(image, graph)

        self.assertEqual(len(nodes), 1)
        orientation = nodes[0].metadata.get('orientation')
        self.assertIsNotNone(orientation)
        self.assertEqual(orientation.get('direction'), 'up')
        self.assertIn('angle_degrees', orientation)


if __name__ == '__main__':
    unittest.main()
