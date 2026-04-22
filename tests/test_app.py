"""Tests for the Gradio web app module."""

import pytest

gradio_available = True
try:
    import gradio  # noqa: F401
except ImportError:
    gradio_available = False


@pytest.mark.skipif(not gradio_available, reason="gradio not installed")
def test_app_module_imports():
    from plot2svg import app  # noqa: F401


@pytest.mark.skipif(not gradio_available, reason="gradio not installed")
def test_build_app_returns_blocks():
    import gradio as gr

    from plot2svg.app import build_app

    demo = build_app()
    assert isinstance(demo, gr.Blocks)


def test_gpu_badge_nonempty():
    from plot2svg.app import _gpu_badge

    badge = _gpu_badge()
    assert isinstance(badge, str)
    assert len(badge) > 0


def test_convert_image_returns_template_preview_and_download():
    from types import SimpleNamespace
    from unittest.mock import patch

    from plot2svg.app import _convert_image

    import shutil

    work_dir = __import__('pathlib').Path('outputs/test-app-template-download')
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    run_dir = work_dir / 'run'
    dl_dir = work_dir / 'dl'
    dl_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / 'input.png'
    input_path.write_bytes(b'fake')

    def fake_run(cfg):
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        enhanced = cfg.output_dir / 'enhanced.png'
        final_svg = cfg.output_dir / 'final.svg'
        scene_graph = cfg.output_dir / 'scene_graph.json'
        template_svg = cfg.output_dir / 'template.svg'
        enhanced.write_bytes(b'png')
        final_svg.write_text('<svg><text>A</text></svg>', encoding='utf-8')
        scene_graph.write_text('{"nodes": []}', encoding='utf-8')
        template_svg.write_text('<svg><rect id="tpl-TXT001"/></svg>', encoding='utf-8')
        return SimpleNamespace(
            enhanced_path=enhanced,
            final_svg_path=final_svg,
            scene_graph_path=scene_graph,
            template_svg_path=template_svg,
        )

    with patch('plot2svg.app.run_pipeline', side_effect=fake_run), patch('plot2svg.app.tempfile.mkdtemp', side_effect=[str(run_dir), str(dl_dir)]):
        result = _convert_image(str(input_path), 'balanced', 'auto', 'opencv', 'deterministic', True, 0)

    preview, svg_html, scene_graph, template_html, svg_file, json_file, template_file = result
    assert preview is not None
    assert 'data:image/svg+xml' in svg_html
    assert scene_graph == {'nodes': []}
    assert 'data:image/svg+xml' in template_html
    assert svg_file.endswith('output.svg')
    assert json_file.endswith('scene_graph.json')
    assert template_file.endswith('template.svg')
    assert __import__('pathlib').Path(template_file).exists()
    shutil.rmtree(work_dir, ignore_errors=True)