import unittest

import numpy as np

from plot2svg.scene_graph import RasterObject, SceneGraph, SceneNode
from plot2svg.semantic_labeling import _looks_like_data_chart, _resolve_semantic_raster_objects


class SemanticLabelingTest(unittest.TestCase):
    def test_looks_like_data_chart_matches_chart_keywords(self) -> None:
        self.assertTrue(_looks_like_data_chart("Kaplan survival curve"))
        self.assertFalse(_looks_like_data_chart("simple icon"))

    def test_resolve_semantic_raster_objects_keeps_chart_like_regions_as_raster(self) -> None:
        image = np.full((180, 220, 3), 255, dtype=np.uint8)
        scene_graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(id='region-metric-panel', type='region', bbox=[20, 20, 180, 140], z_index=1, vector_mode='region_path', confidence=0.9, shape_hint='raster_candidate'),
                SceneNode(id='text-1', type='text', bbox=[24, 144, 170, 166], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Time-dependent AUC curves'),
            ],
        )
        raster_objects = [
            RasterObject(id='raster-region-metric-panel', node_id='region-metric-panel', bbox=[20, 20, 180, 140], image_href='data:image/png;base64,AAAA', metadata={'shape_hint': 'raster_candidate'})
        ]

        updated_graph, kept = _resolve_semantic_raster_objects(image, scene_graph, raster_objects)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].metadata.get('semantic_label'), 'data_chart')
        self.assertEqual(updated_graph.nodes[0].shape_hint, 'data_chart')


if __name__ == "__main__":
    unittest.main()
