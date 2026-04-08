# Plot2SVG Progress

Date: 2026-03-10

## Summary
- The pipeline now supports PNG/JPG/JPEG inputs and produces grouped SVG outputs with editable text.
- OCR normalization and preview generation have been stabilized.
- Box/arrow/container structure detection is now implemented using pure geometric heuristics.
- Scene graph groups carry `shape_type`, `direction`, and `contains_group_ids` metadata.
- SVG output includes `data-shape-type` and `data-direction` attributes on group elements.

## Completed
- Input analysis updated to use generic image metadata (PNG/JPG/JPEG).
- OCR post-processing improved: duplicate word removal and common typo fixes.
- `preview.png` now reuses `enhanced.png` instead of a zero-byte placeholder.
- Scene graph now emits high-level `groups` with roles (`labeled_component`, `text_label`, `connector`).
- SVG export nests group `<g>` elements with role metadata for higher-level editing.
- Structure detection: boxes (labeled regions with text), arrows (connectors with direction), and containers (large regions enclosing >=2 groups).
- GPU acceleration layer (`gpu.py`): transparent CUDA wrappers for GaussianBlur, resize, threshold, Canny, CLAHE, filter2D with automatic CPU fallback.
- OpenCV CUDA wrappers integrated into `enhance.py`, `segment.py`, `vectorize_region.py`, `vectorize_stroke.py`.
- Gradio Web App (`app.py`): drag-and-drop image upload, profile/enhancement selection, SVG preview, scene graph JSON viewer, file downloads.
- `pyproject.toml` updated with declared dependencies and optional extras (`gpu`, `app`, `dev`).
- Test suite passes (62 tests).
- **OCR Pipeline Performance Optimization (6x):**
  - Dual OCR engine: recognition-only engine (`use_text_det=False`) for pre-cropped text regions, full engine for multiline fallback.
  - High-confidence early exit: stop variant loop when any candidate confidence >= 0.85.
  - Pixel variance pre-filter: skip OCR on uniform crops (std < 10.0).
  - Multiline condition tightening: skip multiline fallback when confidence is high.
  - Thread-parallel OCR: `ThreadPoolExecutor(max_workers=4)` in `populate_text_nodes` (ONNX releases GIL).
  - Pipeline-level parallelism: OCR + vectorize_regions + vectorize_strokes run concurrently.

## Current Behavior
- `scene_graph.json` includes both low-level nodes and high-level groups with structure metadata.
- `final.svg` contains nested `<g>` elements with `data-shape-type` and `data-direction` attributes.
- Example group roles: `labeled_region`, `labeled_component`, `text_label`, `connector`, `container`.
- GPU status available via `gpu_status_summary()`: reports OpenCV CUDA, OCR CUDA, and device name.
- Gradio app launches at `http://127.0.0.1:7860` via `plot2svg-app` or `python -m plot2svg.app`.

## New Inputs
- `picture/Gemini_Generated_Image_sw0xj6sw0xj6sw0x.png` has been added and is pending a run with the new grouping logic.

## Known Gaps
- Some low-quality or dense roadmap images still produce weak OCR or fragmented text.
- Performance on wide/complex diagrams significantly improved by OCR pipeline optimization (estimated 4-8x speedup).
- Container detection relies on median-area heuristic; edge cases with many small groups may under-detect.

## Next Steps
- Run the new Gemini image and calibrate thresholds on the output.
- Improve container detection with recursive nesting support.
- Add arrow endpoint snapping to connect arrows to adjacent boxes.
- Add pipeline progress callback for Gradio progress bar.
- Batch processing support in the web app.

## 2026-03-13 Round 13
- `stroke_detector.py` ?????????????????????????????????????????????????????????????
- ??????????????????????????????? `region/node` ???????????????????????
- `graph_builder.py` ??????????????????????????????????????
- `object_svg_exporter.py` ???????????????????? + ?????????????fallback region/stroke ??????????
- Round 13 ????????????????????????????????fallback ????????

## Round 13 Verification
- `pytest -q` -> 143 passed
- ???????
  - `outputs/round13_a22_balanced/final.svg`
  - `outputs/round13_f2_balanced/final.svg`
- ???????
  - `outputs/round13_a22_balanced/debug_lines_mask.png`
  - `outputs/round13_f2_balanced/debug_lines_mask.png`
- ???`a22` ?????????????????????????`F2` ????? 5 ????????????/????????????????

## 2026-03-13 Round 15
- `pipeline.py` ???????????`????/?? -> ????????? -> ????/?? -> ?????????`?
- `ocr.py` ?? `extract_text_overlays(...)` ? `inpaint_text_nodes(...)`???????????????????
- `scene_graph.py` ?? `RasterObject`??????????? `<image href='data:image/png;base64,...'>` ???????? polygon ???
- `object_svg_exporter.py` / `export_svg.py` ??? raster object ?????? `region -> node/raster -> edge -> text` ??????
- ??????????
  - `debug_text_inpaint.png`
  - `debug_nodes_inpaint.png`
  - `debug_strokes_inpaint.png`
  - `debug_lines_mask.png`
  - `debug_region_segmentation.png`
- ?????????????
  - ?? `fan` relation/group??????????????????????
  - ?? `network_container` ???????????? `cluster_region`?
  - ???? node object ??? stage1/stage3 region?????????????????????

## Round 15 Verification
- `pytest -q tests/test_scene_graph.py tests/test_export_svg.py tests/test_ocr.py tests/test_pipeline.py` -> 52 passed
- `pytest -q` -> 147 passed
- ?? `./picture` ??????
  - `picture/F2.png`
  - `picture/orr_signature.png`
  - `picture/a22efeb2-370f-4745-b79c-474a00f105f4.png`
- ???????
  - `outputs/F2/`
  - `outputs/orr_signature/`
  - `outputs/a22-visual/`
  - `outputs/a22-structure/`
  - `outputs/a22-fan/`
  - `outputs/a22-objects/`
  - `outputs/a22-round12-debug/`



## 2026-03-13 Round 16
- `pipeline.py` ?????????`stage1/stage2` proposal mask ?????????????????????? `masks/*.png` ??????
- ??/???????????????? -> ?? -> `cv2.inpaint(...)`???????? bbox ??????????????????????????
- ????????? `stage1` ?? `stroke` ??? `SceneGraph`????????????????????????????????/??????
- `segment.py` ????????????????????????? `raster_candidate`?????????? raster fallback?
- `object_svg_exporter.py` ????????????????????????????????????? polygon?

## Round 16 Verification
- `pytest -q tests/test_pipeline.py tests/test_export_svg.py tests/test_segment.py` -> 36 passed
- `pytest -q` -> 150 passed
- ???????
  - `outputs/F2/final.svg`?????????????`huge_coords = False`
  - `outputs/a22-visual/final.svg`??? 2 ? `<ellipse>` ???`huge_coords = False`
  - `outputs/a22-round12-debug/final.svg`??? 2 ? `<ellipse>` ???`huge_coords = False`
- ????????????
  - `debug_text_inpaint.png`
  - `debug_nodes_inpaint.png`
  - `debug_strokes_inpaint.png`
  - `debug_lines_mask.png`
  - `debug_region_segmentation.png`


## 2026-03-13 Round 17
- `ocr.py`: text inpaint no longer uses large OCR bounding boxes as destructive masks. It now extracts local text-like contours first and only falls back to a very small bbox mask when contour extraction fails.
- `segment.py`: complex icon detection now combines edge contour count, grayscale variance, and significant color count, while explicitly avoiding uniform high-fill background panels.
- `pipeline.py`: raster fallback is now wired into the main pipeline for complex icons, exporting Base64 PNG `<image>` nodes instead of forcing polygon approximation.
- `region_vectorizer.py`: pastel large regions are preserved by relaxing entity rejection. Only tiny extreme monochrome fragments are candidates for early rejection here.
- `object_svg_exporter.py`: final export adds a last-stage large dark region blacklist, so oversized black artifacts are dropped before they can cover labels or containers.

## Round 17 Verification
- `pytest -q tests/test_pipeline.py tests/test_export_svg.py tests/test_segment.py tests/test_ocr.py tests/test_region_vectorizer.py` -> 61 passed
- `pytest -q` -> 153 passed
- Real sample reruns:
  - `outputs/F2-round17/`: `raster_objects = 10`, `<image> = 10`, no dark `class='region'` fragments in `final.svg`
  - `outputs/a22-round17/`: `raster_objects = 8`, `<image> = 8`, `<ellipse> = 2`, no dark `class='region'` fragments in `final.svg`
- Debug artifacts confirmed for both samples:
  - `debug_text_inpaint.png`
  - `debug_nodes_inpaint.png`
  - `debug_strokes_inpaint.png`
  - `debug_lines_mask.png`
  - `debug_region_segmentation.png`
