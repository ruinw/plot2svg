from pathlib import Path
import shutil
import unittest
from uuid import uuid4

from plot2svg.benchmark import run_blind_test_benchmark


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def process_image(self, *, image_path=None, image_base64=None, output_dir=None):
        assert image_path is not None
        self.calls.append(Path(image_path))
        if image_path.stem == 'sample_b':
            return {
                'status': 'error',
                'svg_content': '<svg></svg>',
                'scene_graph': {},
                'error': {'type': 'RuntimeError', 'message': 'failed'},
            }
        return {
            'status': 'ok',
            'svg_content': '<svg></svg>',
            'scene_graph': {
                'graph_edges': [
                    {'id': 'e1', 'path': [[0, 0], [0, 10], [10, 10]], 'metadata': {'route_degraded': False}},
                    {'id': 'e2', 'path': [[10, 10], [20, 20]], 'metadata': {'route_degraded': True}},
                ],
                'icon_objects': [{'id': 'icon-1'}],
                'nodes': [
                    {'id': 'n1', 'shape_hint': 'raster_candidate'},
                    {'id': 'n2', 'shape_hint': 'circle'},
                ],
            },
            'error': None,
        }


class GeneralizationBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path('outputs') / f'test-benchmark-{uuid4().hex}'
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_run_blind_test_benchmark_writes_markdown_report(self) -> None:
        engine = _FakeEngine()
        input_dir = self.base_dir / 'blind'
        output_dir = self.base_dir / 'report'
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / 'sample_a.png').write_bytes(b'a')
        (input_dir / 'sample_b.jpg').write_bytes(b'b')

        result = run_blind_test_benchmark(input_dir=input_dir, output_dir=output_dir, engine=engine)

        self.assertEqual(len(engine.calls), 2)
        self.assertTrue(result['report_path'].exists())
        self.assertIn('| sample_a.png |', result['report_markdown'])
        self.assertIn('| sample_b.jpg |', result['report_markdown'])
        self.assertEqual(result['results'][0]['icon_objects'], 1)
        self.assertEqual(result['results'][0]['raster_candidate_residual'], 1)

    def test_run_blind_test_benchmark_skips_existing_completed_outputs(self) -> None:
        engine = _FakeEngine()
        input_dir = self.base_dir / 'blind-skip'
        output_dir = self.base_dir / 'report-skip'
        input_dir.mkdir(parents=True, exist_ok=True)
        sample_a = input_dir / 'sample_a.png'
        sample_b = input_dir / 'sample_b.jpg'
        sample_a.write_bytes(b'a')
        sample_b.write_bytes(b'b')

        existing_dir = output_dir / 'sample_a'
        existing_dir.mkdir(parents=True, exist_ok=True)
        (existing_dir / 'scene_graph.json').write_text(
            '{"graph_edges": [{"id": "e1", "path": [[0, 0], [0, 10]], "metadata": {"route_degraded": false}}], "icon_objects": [], "nodes": []}',
            encoding='utf-8',
        )
        (existing_dir / 'final.svg').write_text('<svg></svg>', encoding='utf-8')

        result = run_blind_test_benchmark(
            input_dir=input_dir,
            output_dir=output_dir,
            engine=engine,
            skip_existing=True,
        )

        self.assertEqual(engine.calls, [sample_b])
        self.assertEqual(len(result['results']), 2)
        self.assertEqual(result['results'][0]['image'], 'sample_a.png')
        self.assertEqual(result['results'][0]['status'], 'ok')


    def test_run_blind_test_benchmark_filters_image_names(self) -> None:
        engine = _FakeEngine()
        input_dir = self.base_dir / 'blind-filter'
        output_dir = self.base_dir / 'report-filter'
        input_dir.mkdir(parents=True, exist_ok=True)
        sample_a = input_dir / 'sample_a.png'
        sample_b = input_dir / 'sample_b.jpg'
        sample_c = input_dir / 'sample_c.png'
        sample_a.write_bytes(b'a')
        sample_b.write_bytes(b'b')
        sample_c.write_bytes(b'c')

        result = run_blind_test_benchmark(
            input_dir=input_dir,
            output_dir=output_dir,
            engine=engine,
            image_names=['sample_b.jpg', 'sample_c.png'],
        )

        self.assertEqual(engine.calls, [sample_b, sample_c])
        self.assertEqual([item['image'] for item in result['results']], ['sample_b.jpg', 'sample_c.png'])


if __name__ == '__main__':
    default_input_dir = Path('inputs/blind_test_set')
    default_output_dir = Path('outputs/blind_test_benchmark')
    result = run_blind_test_benchmark(input_dir=default_input_dir, output_dir=default_output_dir)
    print(result['report_markdown'])
