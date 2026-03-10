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
