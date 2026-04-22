import base64
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from plot2svg.api import Plot2SvgEngine, process_image
from plot2svg.pipeline import PipelineArtifacts


def _fake_artifacts(output_dir: Path) -> PipelineArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    analyze_path = output_dir / 'analyze.json'
    enhanced_path = output_dir / 'enhanced.png'
    scene_graph_path = output_dir / 'scene_graph.json'
    final_svg_path = output_dir / 'final.svg'
    components_path = output_dir / 'components.json'
    template_svg_path = output_dir / 'template.svg'
    analyze_path.write_text('{}', encoding='utf-8')
    enhanced_path.write_bytes(b'png')
    scene_graph_path.write_text(
        json.dumps({'nodes': [{'id': 'n1'}], 'graph_edges': [], 'icon_objects': []}),
        encoding='utf-8',
    )
    final_svg_path.write_text("<svg><rect width='10' height='10'/></svg>", encoding='utf-8')
    components_path.write_text(json.dumps({'version': 1, 'components': []}), encoding='utf-8')
    template_svg_path.write_text('<svg></svg>', encoding='utf-8')
    return PipelineArtifacts(
        analyze_path=analyze_path,
        enhanced_path=enhanced_path,
        scene_graph_path=scene_graph_path,
        final_svg_path=final_svg_path,
        components_path=components_path,
        template_svg_path=template_svg_path,
    )


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base_dir = Path('outputs') / f'test-api-{uuid4().hex}'
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_process_image_returns_svg_and_scene_graph_from_path(self) -> None:
        image_path = self.base_dir / 'input.png'
        image_path.write_bytes(b'fake-image')

        with patch('plot2svg.api.run_pipeline', side_effect=lambda cfg: _fake_artifacts(cfg.output_dir)):
            result = process_image(image_path=image_path, output_dir=self.base_dir / 'out')

        self.assertEqual(result['status'], 'ok')
        self.assertIn('<svg', result['svg_content'])
        self.assertEqual(result['scene_graph']['nodes'][0]['id'], 'n1')
        self.assertEqual(Path(result['artifacts']['components_path']).name, 'components.json')
        self.assertEqual(Path(result['artifacts']['template_svg_path']).name, 'template.svg')

    def test_engine_passes_template_and_segmentation_options_to_pipeline(self) -> None:
        payload = base64.b64encode(b'fake-image').decode('ascii')
        captured = {}

        def fake_run(cfg):
            captured['segmentation_backend'] = cfg.segmentation_backend
            captured['template_optimization'] = cfg.template_optimization
            captured['emit_layout_template'] = cfg.emit_layout_template
            return _fake_artifacts(cfg.output_dir)

        with patch('plot2svg.api.run_pipeline', side_effect=fake_run):
            engine = Plot2SvgEngine(
                temp_root=self.base_dir / '_tmp',
                segmentation_backend='opencv',
                template_optimization='none',
                emit_layout_template=False,
            )
            result = engine.process_image(image_base64=payload, output_dir=self.base_dir / 'out')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(captured, {
            'segmentation_backend': 'opencv',
            'template_optimization': 'none',
            'emit_layout_template': False,
        })

    def test_process_image_accepts_base64_input(self) -> None:
        payload = base64.b64encode(b'fake-image').decode('ascii')
        with patch('plot2svg.api.run_pipeline', side_effect=lambda cfg: _fake_artifacts(cfg.output_dir)):
            engine = Plot2SvgEngine(temp_root=self.base_dir / '_tmp')
            result = engine.process_image(image_base64=payload, output_dir=self.base_dir / 'out')

        self.assertEqual(result['status'], 'ok')
        self.assertIn('<svg', result['svg_content'])
        self.assertIn('nodes', result['scene_graph'])

    def test_process_image_handles_failures_with_fallback_svg(self) -> None:
        image_path = self.base_dir / 'input.png'
        image_path.write_bytes(b'fake-image')

        with patch('plot2svg.api.run_pipeline', side_effect=RuntimeError('boom')):
            result = process_image(image_path=image_path, output_dir=self.base_dir / 'out')

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error']['type'], 'RuntimeError')
        self.assertIn('boom', result['error']['message'])
        self.assertIn('<svg', result['svg_content'])
        self.assertEqual(result['scene_graph'], {})


if __name__ == '__main__':
    unittest.main()