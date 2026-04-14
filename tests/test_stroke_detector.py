from pathlib import Path
import unittest

import cv2
import numpy as np

from plot2svg.config import PipelineConfig, ThresholdConfig
from plot2svg.scene_graph import SceneGraph, SceneNode
from plot2svg.stroke_detector import _build_stroke_mask, _should_reconstruct_dense_lines, detect_strokes, is_stroke_sane


class StrokeDetectorTest(unittest.TestCase):
    def test_detect_strokes_returns_polyline(self) -> None:
        image = np.full((80, 160), 255, dtype=np.uint8)
        cv2.line(image, (10, 40), (130, 40), 0, 3)
        graph = SceneGraph(
            width=160,
            height=80,
            nodes=[
                SceneNode(id='stroke-1', type='stroke', bbox=[0, 20, 150, 60], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertGreaterEqual(len(primitives[0].points), 2)
        self.assertEqual(primitives[0].node_id, 'stroke-1')

    def test_detect_strokes_detects_arrow_head(self) -> None:
        image = np.full((100, 180), 255, dtype=np.uint8)
        cv2.line(image, (20, 50), (120, 50), 0, 3)
        triangle = np.array([[120, 40], [120, 60], [160, 50]], dtype=np.int32)
        cv2.fillConvexPoly(image, triangle, 0)
        graph = SceneGraph(
            width=180,
            height=100,
            nodes=[
                SceneNode(id='stroke-arrow', type='stroke', bbox=[10, 30, 170, 70], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertIsNotNone(primitives[0].arrow_head)

    def test_detect_strokes_keeps_low_contrast_line_on_tinted_background(self) -> None:
        image = np.full((120, 220), 210, dtype=np.uint8)
        cv2.rectangle(image, (20, 25), (200, 95), 222, -1)
        cv2.line(image, (30, 60), (190, 60), 160, 2)
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[
                SceneNode(id='stroke-low-contrast', type='stroke', bbox=[20, 30, 200, 90], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertGreaterEqual(len(primitives[0].points), 2)
        xs = [point[0] for point in primitives[0].points]
        self.assertLess(min(xs), 80)
        self.assertGreater(max(xs), 140)

    def test_detect_strokes_uses_adaptive_path_on_gradient_background(self) -> None:
        image = np.tile(np.linspace(214, 238, 260, dtype=np.uint8), (120, 1))
        cv2.line(image, (30, 68), (220, 44), 150, 1)
        graph = SceneGraph(
            width=260,
            height=120,
            nodes=[
                SceneNode(id='stroke-gradient', type='stroke', bbox=[20, 30, 230, 80], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertGreaterEqual(len(primitives[0].points), 2)
        self.assertIn('adaptive', primitives[0].metadata.get('detector_mode', ''))
        xs = [point[0] for point in primitives[0].points]
        self.assertLess(min(xs), 90)
        self.assertGreater(max(xs), 180)

    def test_detect_strokes_uses_clahe_for_very_low_contrast_line(self) -> None:
        image = np.full((120, 240), 224, dtype=np.uint8)
        cv2.ellipse(image, (120, 60), (92, 38), 0, 0, 360, 230, -1)
        cv2.line(image, (46, 60), (194, 60), 206, 1)
        graph = SceneGraph(
            width=240,
            height=120,
            nodes=[
                SceneNode(id='stroke-clahe-low-contrast', type='stroke', bbox=[38, 32, 202, 88], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertIn('clahe', primitives[0].metadata.get('detector_mode', ''))
        xs = [point[0] for point in primitives[0].points]
        self.assertLess(min(xs), 90)
        self.assertGreater(max(xs), 150)

    def test_detect_strokes_absorbs_nearby_triangle_arrow_head(self) -> None:
        image = np.full((120, 220), 220, dtype=np.uint8)
        cv2.line(image, (25, 60), (150, 60), 60, 2)
        triangle = np.array([[156, 50], [156, 70], [188, 60]], dtype=np.int32)
        cv2.fillConvexPoly(image, triangle, 70)
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[
                SceneNode(id='stroke-gap-arrow', type='stroke', bbox=[20, 40, 192, 80], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertIsNotNone(primitives[0].arrow_head)
        self.assertTrue(primitives[0].metadata.get('arrow_absorbed', False))

    def test_detect_strokes_limits_arrowhead_area_relative_to_line_width(self) -> None:
        image = np.full((120, 220), 220, dtype=np.uint8)
        cv2.line(image, (25, 60), (150, 60), 60, 2)
        triangle = np.array([[156, 50], [156, 70], [188, 60]], dtype=np.int32)
        cv2.fillConvexPoly(image, triangle, 70)
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[
                SceneNode(id='stroke-area-arrow', type='stroke', bbox=[20, 40, 192, 80], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        arrow = primitives[0].arrow_head
        self.assertIsNotNone(arrow)
        pts = [arrow['tip'], arrow['left'], arrow['right']]
        area = abs(sum(pts[i][0] * pts[(i + 1) % 3][1] - pts[(i + 1) % 3][0] * pts[i][1] for i in range(3))) / 2.0
        self.assertLess(area, 120.0)

    def test_detect_strokes_does_not_absorb_backward_facing_triangle(self) -> None:
        image = np.full((120, 220), 220, dtype=np.uint8)
        cv2.line(image, (25, 60), (150, 60), 60, 2)
        triangle = np.array([[130, 60], [170, 50], [170, 70]], dtype=np.int32)
        cv2.fillConvexPoly(image, triangle, 70)
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[
                SceneNode(id='stroke-backward-arrow', type='stroke', bbox=[20, 40, 192, 80], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertFalse(primitives[0].metadata.get('arrow_absorbed', False))

    def test_detect_strokes_keeps_very_low_contrast_single_line_as_single_primitive(self) -> None:
        image = np.tile(np.linspace(228, 236, 260, dtype=np.uint8), (120, 1))
        cv2.line(image, (28, 66), (220, 48), 210, 1)
        graph = SceneGraph(
            width=260,
            height=120,
            nodes=[
                SceneNode(id='stroke-very-low-contrast', type='stroke', bbox=[20, 30, 230, 82], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertFalse(primitives[0].metadata.get('dense_reconstruction', False))

    def test_is_stroke_sane_rejects_global_span_hallucination(self) -> None:
        self.assertFalse(
            is_stroke_sane(
                [[10.0, 100.0], [950.0, 102.0]],
                image_width=1000,
                image_height=400,
                stroke_width=6.0,
            )
        )

    def test_is_stroke_sane_rejects_absurd_width(self) -> None:
        self.assertFalse(
            is_stroke_sane(
                [[40.0, 40.0], [140.0, 42.0]],
                image_width=300,
                image_height=200,
                stroke_width=2155.0,
            )
        )
    def test_is_stroke_sane_rejects_canvas_spanning_hallucination(self) -> None:
        self.assertFalse(is_stroke_sane([[10.0, 40.0], [195.0, 42.0]], image_width=200, image_height=100, stroke_width=4.0))

    def test_is_stroke_sane_rejects_absurd_stroke_width(self) -> None:
        self.assertFalse(is_stroke_sane([[20.0, 30.0], [140.0, 36.0]], image_width=200, image_height=100, stroke_width=31.0))

    def test_is_stroke_sane_respects_custom_width_threshold(self) -> None:
        cfg = PipelineConfig(
            input_path='picture/F2.png',
            output_dir='outputs/F2',
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                stroke_sane_canvas_span_ratio=0.8,
                stroke_sane_max_width=40.0,
            ),
        )

        self.assertTrue(
            is_stroke_sane(
                [[20.0, 30.0], [140.0, 36.0]],
                image_width=200,
                image_height=100,
                stroke_width=31.0,
                thresholds=cfg.thresholds,
            )
        )


    def test_detect_strokes_drops_short_isolated_segment(self) -> None:
        image = np.full((60, 80), 255, dtype=np.uint8)
        cv2.line(image, (20, 30), (30, 30), 0, 2)
        graph = SceneGraph(
            width=80,
            height=60,
            nodes=[
                SceneNode(id='stroke-short', type='stroke', bbox=[18, 24, 34, 36], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(primitives, [])

    def test_detect_strokes_respects_custom_min_polyline_length(self) -> None:
        image = np.full((60, 80), 255, dtype=np.uint8)
        cv2.line(image, (20, 30), (30, 30), 0, 2)
        graph = SceneGraph(
            width=80,
            height=60,
            nodes=[
                SceneNode(id='stroke-short', type='stroke', bbox=[18, 24, 34, 36], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )
        cfg = PipelineConfig(
            input_path='picture/F2.png',
            output_dir='outputs/F2',
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                stroke_min_polyline_length=5.0,
            ),
        )

        primitives = detect_strokes(image, graph, cfg=cfg)

        self.assertEqual(len(primitives), 1)


    def test_dense_reconstruction_skips_oversized_masks(self) -> None:
        mask = np.full((720, 1380), 255, dtype=np.uint8)
        skeleton = np.full((720, 1380), 255, dtype=np.uint8)

        self.assertFalse(_should_reconstruct_dense_lines(mask, skeleton, True))

    def test_dense_reconstruction_respects_custom_thresholds(self) -> None:
        mask = np.full((120, 120), 255, dtype=np.uint8)
        skeleton = np.full((120, 120), 255, dtype=np.uint8)
        cfg = PipelineConfig(
            input_path='picture/F2.png',
            output_dir='outputs/F2',
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                stroke_dense_min_mask_pixels=10,
                stroke_dense_min_trace_pixels=10,
                stroke_dense_min_width=10,
                stroke_dense_min_height=10,
                stroke_dense_max_area=50000,
                stroke_dense_max_mask_pixels=50000,
                stroke_dense_max_trace_pixels=50000,
                stroke_dense_min_fill_ratio=0.01,
            ),
        )

        self.assertTrue(_should_reconstruct_dense_lines(mask, skeleton, True, thresholds=cfg.thresholds))

    def test_detect_strokes_reconstructs_dense_fan_into_multiple_lines(self) -> None:
        image = np.full((150, 240), 255, dtype=np.uint8)
        for offset in range(-40, 41, 10):
            cv2.line(image, (28, 75 + offset), (190, 75), 0, 3)
        graph = SceneGraph(
            width=240,
            height=150,
            nodes=[
                SceneNode(id='stroke-fan-dense', type='stroke', bbox=[20, 25, 200, 125], z_index=1, vector_mode='stroke_path', confidence=0.9)
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertGreaterEqual(len(primitives), 3)
        self.assertTrue(all(primitive.metadata.get('used_skeleton', False) for primitive in primitives))
        self.assertTrue(any(primitive.metadata.get('dense_reconstruction', False) for primitive in primitives))
        self.assertTrue(all('dense-lines' in primitive.metadata.get('detector_mode', '') for primitive in primitives))

    def test_detect_strokes_records_absorbed_triangle_region_anchor(self) -> None:
        image = np.full((120, 220), 220, dtype=np.uint8)
        cv2.line(image, (25, 60), (150, 60), 60, 2)
        triangle = np.array([[156, 50], [156, 70], [188, 60]], dtype=np.int32)
        cv2.fillConvexPoly(image, triangle, 70)
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[
                SceneNode(id='stroke-gap-arrow', type='stroke', bbox=[20, 40, 192, 80], z_index=1, vector_mode='stroke_path', confidence=0.9),
                SceneNode(id='triangle-region-1', type='region', bbox=[156, 50, 188, 70], z_index=2, vector_mode='region_path', confidence=0.9, shape_hint='triangle'),
            ],
        )

        primitives = detect_strokes(image, graph)

        self.assertEqual(len(primitives), 1)
        self.assertTrue(primitives[0].metadata.get('arrow_absorbed', False))
        self.assertIn('triangle-region-1', primitives[0].metadata.get('absorbed_region_ids', []))

    def test_build_stroke_mask_handles_tiny_float_crop(self) -> None:
        crop = np.array([[12.5]], dtype=np.float32)

        mask, mode = _build_stroke_mask(crop)

        self.assertEqual(mask.shape, (1, 1))
        self.assertEqual(mask.dtype, np.uint8)
        self.assertEqual(mode, 'tiny-crop')

if __name__ == '__main__':
    unittest.main()


