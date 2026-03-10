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
- Performance on wide/complex diagrams remains slow under the `balanced` profile.
- Container detection relies on median-area heuristic; edge cases with many small groups may under-detect.

## Next Steps
- Run the new Gemini image and calibrate thresholds on the output.
- Improve container detection with recursive nesting support.
- Add arrow endpoint snapping to connect arrows to adjacent boxes.
- Add pipeline progress callback for Gradio progress bar.
- Batch processing support in the web app.
