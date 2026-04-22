import json
from pathlib import Path
import unittest

from plot2svg.artifact_metrics import compute_artifact_metrics


class ArtifactMetricsTest(unittest.TestCase):
    def test_compute_artifact_metrics_counts_scene_graph_and_svg_primitives(self) -> None:
        scene_graph = _sample_scene_graph()
        svg = _sample_svg()

        metrics = compute_artifact_metrics(scene_graph, svg)

        self.assertEqual(metrics['node_count'], 4)
        self.assertEqual(metrics['text_count'], 1)
        self.assertEqual(metrics['region_count'], 1)
        self.assertEqual(metrics['stroke_count'], 1)
        self.assertEqual(metrics['icon_count'], 1)
        self.assertEqual(metrics['raster_fallback_count'], 1)
        self.assertEqual(metrics['graph_edge_count'], 1)
        self.assertEqual(metrics['svg_text_count'], 1)
        self.assertEqual(metrics['svg_shape_count'], 3)
        self.assertEqual(metrics['svg_path_count'], 1)
        self.assertEqual(metrics['svg_image_count'], 1)

    def test_synthetic_baseline_fixture_matches_computed_metrics(self) -> None:
        baseline_path = Path('tests/fixtures/autofigure_reference_baseline.json')
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))

        self.assertEqual(compute_artifact_metrics(_sample_scene_graph(), _sample_svg()), baseline['metrics'])


def _sample_scene_graph() -> dict[str, object]:
    return {
        'nodes': [
            {'id': 'background-root', 'type': 'background'},
            {'id': 'text-1', 'type': 'text'},
            {'id': 'region-1', 'type': 'region'},
            {'id': 'stroke-1', 'type': 'stroke'},
        ],
        'icon_objects': [{'id': 'icon-1'}],
        'raster_objects': [{'id': 'raster-1'}],
        'graph_edges': [{'id': 'edge-1'}],
    }


def _sample_svg() -> str:
    return """
    <svg><text id='text-1'>A</text><rect id='r1'/><circle id='c1'/>
    <ellipse id='e1'/><path id='p1'/><image id='img1'/></svg>
    """


if __name__ == '__main__':
    unittest.main()