"""Gradio Web App for Plot2SVG.

Launch with ``python -m plot2svg.app`` or the ``plot2svg-app`` console script.
Requires the *app* optional dependency group (``pip install plot2svg[app]``).
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
from pathlib import Path

from .config import PipelineConfig
from .gpu import gpu_status_summary
from .pipeline import run_pipeline


def _require_gradio():
    """Import and return gradio, raising a helpful error if absent."""
    try:
        import gradio as gr
        return gr
    except ImportError as exc:
        raise ImportError(
            "Gradio is required for the web app. Install with: pip install plot2svg[app]"
        ) from exc


# ---------------------------------------------------------------------------
# GPU status badge
# ---------------------------------------------------------------------------

def _gpu_badge() -> str:
    """Return a Markdown badge reflecting current GPU availability."""
    status = gpu_status_summary()
    if status["opencv_cuda"]:
        return f"### 🟢 Full GPU Acceleration — {status['device_name']}"
    if status["ocr_cuda"]:
        return (
            "### 🟢 GPU Accelerated — OCR runs on CUDA "
            "(image processing uses CPU, which is faster for these operations)"
        )
    return "### ⚪ CPU Mode — install onnxruntime-gpu for GPU acceleration"


# ---------------------------------------------------------------------------
# Core conversion logic
# ---------------------------------------------------------------------------

def _convert_image(
    image_path: str | None,
    profile: str,
    enhancement_mode: str,
) -> tuple[str | None, str, str, str | None, str | None]:
    """Run the pipeline and return artifacts for the Gradio UI.

    Returns (preview_path, svg_html, scene_graph_json, svg_file, json_file).
    """
    if not image_path:
        return None, "<p>Please upload an image first.</p>", "{}", None, None

    tmpdir = tempfile.mkdtemp(prefix="plot2svg_")
    try:
        cfg = PipelineConfig(
            input_path=Path(image_path),
            output_dir=Path(tmpdir),
            execution_profile=profile.lower(),
            enhancement_mode=enhancement_mode.lower().replace(" ", "_"),
        )
        artifacts = run_pipeline(cfg)

        svg_content = artifacts.final_svg_path.read_text(encoding="utf-8")
        sg_json_str = artifacts.scene_graph_path.read_text(encoding="utf-8")
        sg_data = json.loads(sg_json_str)
        preview = str(artifacts.enhanced_path)

        svg_b64 = base64.b64encode(svg_content.encode("utf-8")).decode("ascii")
        svg_html = (
            f"<img src='data:image/svg+xml;base64,{svg_b64}' "
            f"style='max-width:100%;height:auto;border:1px solid #ccc;' />"
        )

        # Persist download files outside tmpdir so Gradio can serve them.
        dl_dir = Path(tempfile.mkdtemp(prefix="plot2svg_dl_"))
        svg_dl = dl_dir / "output.svg"
        json_dl = dl_dir / "scene_graph.json"
        shutil.copy2(artifacts.final_svg_path, svg_dl)
        shutil.copy2(artifacts.scene_graph_path, json_dl)

        return preview, svg_html, sg_data, str(svg_dl), str(json_dl)

    except Exception as exc:
        error_html = f"<p style='color:red;'>Error: {exc}</p>"
        return None, error_html, "{}", None, None


# ---------------------------------------------------------------------------
# Build the Gradio Blocks UI
# ---------------------------------------------------------------------------

def build_app():
    """Construct and return a ``gr.Blocks`` app (not yet launched)."""
    gr = _require_gradio()

    with gr.Blocks(title="Plot2SVG") as demo:
        gr.Markdown("# Plot2SVG — PNG to Editable SVG")
        gr.Markdown(_gpu_badge())

        with gr.Row():
            # ---- Left: controls ------------------------------------------------
            with gr.Column(scale=1):
                input_image = gr.Image(
                    type="filepath",
                    label="Upload Image",
                    sources=["upload", "clipboard"],
                )
                profile_radio = gr.Radio(
                    choices=["speed", "balanced", "quality"],
                    value="balanced",
                    label="Execution Profile",
                )
                enhance_radio = gr.Radio(
                    choices=["auto", "skip", "light", "sr_x2", "sr_x4"],
                    value="auto",
                    label="Enhancement Mode",
                )
                convert_btn = gr.Button("Convert", variant="primary")

            # ---- Right: results ------------------------------------------------
            with gr.Column(scale=2):
                with gr.Tabs():
                    with gr.TabItem("Preview"):
                        preview_image = gr.Image(label="Enhanced Preview", interactive=False)
                    with gr.TabItem("SVG"):
                        svg_display = gr.HTML(label="SVG Output")
                    with gr.TabItem("Scene Graph"):
                        sg_json = gr.JSON(label="Scene Graph")

                with gr.Row():
                    svg_file = gr.File(label="Download SVG")
                    json_file = gr.File(label="Download JSON")

        convert_btn.click(
            fn=_convert_image,
            inputs=[input_image, profile_radio, enhance_radio],
            outputs=[preview_image, svg_display, sg_json, svg_file, json_file],
        )

        gr.Markdown(
            "---\n"
            "*Plot2SVG* — Convert raster plots and diagrams into "
            "component-editable SVG files."
        )

    return demo


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the Gradio web app."""
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)


if __name__ == "__main__":
    main()
