from pathlib import Path
import unittest

import cv2
import numpy as np

from plot2svg.region_vectorizer import vectorize_region_objects
from plot2svg.scene_graph import SceneGraph, SceneNode


class RegionVectorizerTest(unittest.TestCase):
    def test_vectorize_region_objects_marks_large_dense_panel_as_rectangle(self) -> None:
        image = np.full((240, 360, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (24, 32), (336, 208), (252, 224, 196), -1)

        graph = SceneGraph(
            width=360,
            height=240,
            nodes=[
                SceneNode(
                    id='region-panel',
                    type='region',
                    bbox=[24, 32, 336, 208],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.95,
                    fill='#c4e0fc',
                    fill_opacity=0.9,
                    stroke='#c48ef2',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].metadata.get('shape_type'), 'rectangle')
        self.assertTrue(objects[0].metadata.get('entity_valid', False))
        self.assertEqual(objects[0].holes, [])

    def test_vectorize_region_objects_respects_layout_panel_hint_as_rectangle(self) -> None:
        image = np.full((220, 400, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 14), (190, 206), (232, 216, 232), -1)
        cv2.putText(image, 'Panel', (54, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 10, cv2.LINE_AA)

        graph = SceneGraph(
            width=400,
            height=220,
            nodes=[
                SceneNode(
                    id='panel-region-001',
                    type='region',
                    bbox=[0, 0, 210, 220],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.99,
                    fill='#e8d8e8',
                    fill_opacity=0.92,
                    stroke='#e8d8e8',
                    shape_hint='panel',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].metadata.get('shape_type'), 'rectangle')
        self.assertEqual(objects[0].holes, [])
        rectangle = objects[0].metadata.get('rectangle') or {}
        self.assertEqual(rectangle.get('x'), 0.0)
        self.assertEqual(rectangle.get('y'), 0.0)
        self.assertEqual(rectangle.get('width'), 210.0)
        self.assertEqual(rectangle.get('height'), 220.0)

    def test_vectorize_region_objects_prefers_ellipse_metadata_for_large_ellipse(self) -> None:
        image = np.full((240, 240, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (120, 120), (70, 50), 18, 0, 360, (214, 194, 226), -1)

        graph = SceneGraph(
            width=240,
            height=240,
            nodes=[
                SceneNode(
                    id='region-ellipse',
                    type='region',
                    bbox=[42, 56, 198, 184],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.95,
                    fill='#e2c2d6',
                    fill_opacity=0.8,
                    stroke='#775577',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].metadata.get('shape_type'), 'ellipse')
        self.assertTrue(objects[0].metadata.get('entity_valid', True))
        ellipse = objects[0].metadata.get('ellipse') or {}
        self.assertGreater(ellipse.get('rx', 0), 40)
        self.assertGreater(ellipse.get('ry', 0), 25)
        self.assertLess(abs(ellipse.get('rotation', 0) - 18), 12)

    def test_vectorize_region_objects_keeps_ellipse_when_interior_has_holes(self) -> None:
        image = np.full((280, 280, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (140, 140), (90, 70), 0, 0, 360, (214, 194, 226), -1)
        cv2.putText(image, 'ABC', (102, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 8, cv2.LINE_AA)
        cv2.line(image, (80, 140), (200, 140), (255, 255, 255), 4, cv2.LINE_AA)

        graph = SceneGraph(
            width=280,
            height=280,
            nodes=[
                SceneNode(
                    id='region-hole-ellipse',
                    type='region',
                    bbox=[48, 68, 232, 212],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.95,
                    fill='#e2c2d6',
                    fill_opacity=0.5,
                    stroke='#775577',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].metadata.get('shape_type'), 'ellipse')
        self.assertTrue(objects[0].metadata.get('entity_valid', True))
        ellipse = objects[0].metadata.get('ellipse') or {}
        self.assertGreater(ellipse.get('rx', 0), 60)
        self.assertGreater(ellipse.get('ry', 0), 45)
        self.assertLess(ellipse.get('fit_error', 1), 0.2)

    def test_vectorize_region_objects_keeps_colored_pastel_region_valid(self) -> None:
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        points = np.array([[44, 44], [78, 48], [72, 72], [52, 80], [40, 60]], dtype=np.int32)
        cv2.fillConvexPoly(image, points, (248, 246, 232))

        graph = SceneGraph(
            width=120,
            height=120,
            nodes=[
                SceneNode(
                    id='region-pastel',
                    type='region',
                    bbox=[36, 40, 82, 84],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.55,
                    fill='#e8f6f8',
                    fill_opacity=0.35,
                    stroke='#e8f6f8',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertTrue(objects[0].metadata.get('entity_valid', False))
        self.assertIsNone(objects[0].metadata.get('reject_reason'))


    def test_vectorize_region_objects_does_not_emit_bbox_path_for_empty_region(self) -> None:
        image = np.full((80, 80, 3), 255, dtype=np.uint8)
        graph = SceneGraph(
            width=80,
            height=80,
            nodes=[
                SceneNode(
                    id='region-empty',
                    type='region',
                    bbox=[10, 10, 60, 60],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.4,
                    fill='#ffffff',
                    fill_opacity=1.0,
                    stroke='#000000',
                )
            ],
        )

        objects = vectorize_region_objects(image, graph)

        self.assertEqual(len(objects), 1)
        self.assertFalse(objects[0].metadata.get('entity_valid', True))
        self.assertEqual(objects[0].outer_path, '')
        self.assertEqual(objects[0].holes, [])

if __name__ == '__main__':
    unittest.main()
