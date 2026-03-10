# Plot2SVG

Convert raster plots and diagrams (PNG/JPG/JPEG) into component-editable SVG files.

Plot2SVG is an engineering-oriented MVP that takes low-quality or complex raster images and produces structured, grouped SVG output with editable text, region contours, and stroke paths.

## Features

- **Input routing** — auto-classifies images as `small_lowres`, `wide_hires`, `signature_lineart`, or `flat_graphics`
- **Image enhancement** — denoising, CLAHE contrast, sharpening, conservative super-resolution
- **Component segmentation** — extracts `region`, `stroke`, and `text_like` proposals with overlap merging
- **Scene graph** — structured intermediate representation with nodes, groups, and structure metadata
- **OCR** — text node merging, multi-candidate selection, multi-line fallback, GPU-accelerated via ONNX Runtime
- **Structure detection** — boxes, arrows, and containers identified via geometric heuristics
- **Vectorization** — contour-based region paths and stroke/line-art paths
- **SVG export** — grouped `<g>` elements with `data-shape-type` and `data-direction` attributes
- **GPU acceleration** — transparent CUDA wrappers for OpenCV operations with automatic CPU fallback
- **Web App** — Gradio-based UI for drag-and-drop conversion

## Installation

```bash
pip install -e .
```

### Optional extras

```bash
pip install -e ".[app]"    # Gradio web app
pip install -e ".[gpu]"    # onnxruntime-gpu for OCR acceleration
pip install -e ".[dev]"    # pytest + coverage
```

> **Note:** `onnxruntime` and `onnxruntime-gpu` conflict — install only one. The `gpu` extra replaces the base ONNX Runtime.

## Quick Start

### CLI

```bash
# Default balanced mode
plot2svg --input image.png --output result/

# Choose execution profile
plot2svg --input image.png --output result/ --profile speed
plot2svg --input image.png --output result/ --profile quality

# Specify enhancement mode
plot2svg --input image.png --output result/ --enhancement-mode sr_x2
```

### Web App

```bash
plot2svg-app
```

Opens a browser at `http://127.0.0.1:7860` with:
- Drag-and-drop image upload
- Execution profile and enhancement mode selection
- Tabs for preview, SVG output, and scene graph JSON
- Download buttons for SVG and JSON files
- GPU status indicator

### Python API

```python
from plot2svg import PipelineConfig, run_pipeline

cfg = PipelineConfig(
    input_path="image.png",
    output_dir="result/",
    execution_profile="balanced",
    enhancement_mode="auto",
)
artifacts = run_pipeline(cfg)
print(artifacts.final_svg_path)
```

## Execution Profiles

| Profile | Behavior |
|---------|----------|
| `speed` | Smaller proposal bounds, aggressive text skip, fewer OCR variants |
| `balanced` | Default — reasonable trade-off between speed and quality |
| `quality` | Larger proposal bounds, relaxed text retention, more OCR variants |

## Output Artifacts

```
output_dir/
├── analyze.json          # Input analysis and routing
├── enhance.json          # Enhancement strategy and scale factor
├── enhanced.png          # Enhanced raster image
├── components_raw.json   # Raw component proposals
├── scene_graph.json      # Structured intermediate representation
├── final.svg             # Grouped, editable SVG output
├── preview.png           # Quick preview (reuses enhanced image)
└── masks/                # Per-component binary masks
```

## GPU Acceleration

Plot2SVG transparently uses GPU acceleration when available:

| Backend | Operations | Requirement |
|---------|-----------|-------------|
| OpenCV CUDA | GaussianBlur, resize, threshold, Canny, CLAHE, filter2D | OpenCV built with CUDA |
| ONNX Runtime CUDA | OCR inference | `pip install onnxruntime-gpu` |

Check GPU status:

```python
from plot2svg import gpu_status_summary
print(gpu_status_summary())
# {'opencv_cuda': False, 'ocr_cuda': True, 'device_name': 'CPU'}
```

- Small images (< 512px) always use CPU to avoid GPU transfer overhead
- All GPU operations fall back to CPU on any error

## Project Structure

```
src/plot2svg/
├── __init__.py             # Public API
├── analyze.py              # Input analysis and routing
├── app.py                  # Gradio web app
├── cli.py                  # CLI entry point
├── config.py               # Pipeline configuration
├── detect_structure.py     # Box/arrow/container detection
├── enhance.py              # Image enhancement
├── export_svg.py           # SVG assembly and export
├── gpu.py                  # GPU detection and CUDA wrappers
├── ocr.py                  # Text recognition
├── pipeline.py             # Top-level orchestration
├── scene_graph.py          # Intermediate representation
├── segment.py              # Component proposal generation
├── vectorize_region.py     # Region contour vectorization
└── vectorize_stroke.py     # Stroke/line-art vectorization
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

62 tests covering all pipeline stages.

## Current Limitations

- Single-image processing only (no batch mode)
- OCR accuracy varies on dense or low-quality text
- Wide/complex diagrams can be slow under `balanced` profile
- OpenCV CUDA requires a custom-built OpenCV (pip version is CPU-only)

## License

[MIT](LICENSE)
