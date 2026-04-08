# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Plot2SVG converts raster plots/diagrams (PNG/JPG/JPEG) into component-editable SVG files. The project is actively under development and debugging — no production-ready version exists yet. The pipeline uses classical CV (OpenCV + ONNX Runtime OCR), no LLMs.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_pipeline.py -v

# Run a specific test
pytest tests/test_scene_graph.py::SceneGraphTest::test_build_scene_graph -v

# Coverage
pytest --cov=plot2svg --cov-report=term-missing tests/

# CLI usage
plot2svg --input image.png --output result/
plot2svg --input image.png --output result/ --profile quality

# Web app (Gradio at localhost:7860, requires [app] extra)
plot2svg-app

# Python API
from plot2svg import PipelineConfig, run_pipeline
```

## Architecture: Subtraction-Based Pipeline

The pipeline is NOT a single-pass trace. It uses a **subtraction protocol**: each stage detects elements, removes them from the working image via `cv2.inpaint()`, then the next stage works on the cleaned image. This prevents double-detection.

A `global_ignore_mask` accumulates all resolved regions across stages.

```
Input Image
  │
  ├─ analyze.py          → route classification (small_lowres/wide_hires/signature_lineart/flat_graphics)
  ├─ enhance.py          → denoise, CLAHE, sharpen, optional super-resolution
  │
  ├─ text_layers.py      → separate text vs graphic layers
  ├─ ocr.py              → extract_text_overlays() + inpaint_text_nodes() → text removed from image
  │
  ├─ Stage 1 (segment.py + node_detector.py + icon_processor.py)
  │   → detect node-like primitives and icons → inpaint them away
  │
  ├─ Stage 2 (segment.py + stroke_detector.py)
  │   → detect strokes/lines from node-cleaned image → inpaint them away
  │
  ├─ Stage 3 (segment.py + region_vectorizer.py)
  │   → vectorize remaining large background/container regions
  │
  ├─ scene_graph.py      → assemble all stages into unified SceneGraph
  ├─ detect_structure.py → box/arrow/container heuristic detection
  ├─ layout_refiner.py   → text de-duplication, overlap resolution
  ├─ router.py           → A* orthogonal routing for semantic connectors
  └─ export_svg.py       → grouped <g> elements with data-shape-type attributes
```

## Key Data Types (scene_graph.py)

`SceneGraph` is the central protocol layer — all downstream processing reads from it.

| Type | Role |
|------|------|
| `SceneNode` | Low-level component (region/stroke/text/background) with bbox, fill, z_index |
| `SceneGroup` | Higher-level group with role (labeled_component, connector, container) |
| `SceneRelation` | Explicit relationship between nodes/groups (fan, connector) |
| `SceneObject` | Semantic object assembled from nodes and groups |
| `StrokePrimitive` | Traced polyline with width and optional arrowhead |
| `NodeObject` | Detected graph node (circle primitive with center/radius) |
| `RegionObject` | Mask-based vector region with outer_path and holes |
| `IconObject` | Compound-path icon with even-odd fill rule |
| `RasterObject` | Fallback Base64 `<image>` for icons that can't be vectorized |
| `GraphEdge` | Reconstructed connection between anchors with routed path |

## Pipeline Orchestration (pipeline.py)

`run_pipeline(cfg: PipelineConfig) -> PipelineArtifacts` orchestrates everything. Key patterns:

- `_inpaint_*` functions use `cv2.inpaint()` to erase detected elements
- Stage assembly via `_assemble_scene_graph()` merges stage1/stage2/stage3 graphs + text + objects
- Post-assembly passes: `promote_component_groups` → `detect_structures` → `_inject_fan_relation` → layout/routing

## Configuration (config.py)

`PipelineConfig` controls execution. Key fields:

- `execution_profile`: `speed` | `balanced` (default) | `quality` — affects proposal bounds, OCR variants, text skip thresholds
- `enhancement_mode`: `auto` | `skip` | `light` | `sr_x2` | `sr_x4`
- `enable_shape_detection`: toggles box/arrow/container detection
- Profile-dependent methods: `proposal_max_side()`, `text_skip_min_width()`, `ocr_variant_count()`

## Module Topology (newer modules not in README)

| Module | Purpose |
|--------|---------|
| `text_layers.py` | Separate text/graphic layers before segmentation |
| `node_detector.py` | Detect circular/elliptical node primitives |
| `icon_processor.py` | Cluster and validate icon fragments |
| `icon_vectorizer.py` | Compound-path vectorization for clean icons |
| `stroke_detector.py` | Line/edge detection with Hough and skeleton tracing |
| `region_vectorizer.py` | Hierarchical contour vectorization for regions |
| `graph_builder.py` | Build graph edges from stroke primitives + node anchors |
| `object_svg_exporter.py` | SVG element generation per object type |
| `router.py` | A* orthogonal routing for semantic connectors |
| `layout_refiner.py` | Text de-duplication, overlap nudging, anchor sync |
| `svg_templates.py` | Template matching for known shapes (arrow, diamond, etc.) |
| `image_io.py` | Unified image read/write (handles path vs ndarray) |
| `api.py` | `Plot2SvgEngine` — stable external API wrapper |
| `benchmark.py` | Blind-test benchmarking over image directories |

## Output Artifacts

Each run produces in `output_dir/`:
- `analyze.json`, `scene_graph.json`, `final.svg`, `enhanced.png`
- Debug images: `debug_text_inpaint.png`, `debug_nodes_inpaint.png`, `debug_strokes_inpaint.png`, `debug_lines_mask.png`, `debug_region_segmentation.png`

## Debugging Tips

- Always check `debug_*.png` files to understand what each stage sees
- `scene_graph.json` is the single source of truth — inspect it to diagnose misclassification
- The `sandbox/` directory contains experimental scripts for isolated testing
- Test images go in `inputs/`; outputs go in `output/`

## Dependencies

- Python >=3.11, OpenCV, NumPy, Pillow, rapidocr-onnxruntime, onnxruntime
- `onnxruntime` and `onnxruntime-gpu` conflict — install only one
- Source layout: `src/plot2svg/` (setuptools src-layout), tests in `tests/`
