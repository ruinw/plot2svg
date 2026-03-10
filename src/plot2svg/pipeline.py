"""Top-level pipeline orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2

from .analyze import analyze_image
from .config import PipelineConfig
from .enhance import enhance_image
from .export_svg import export_svg
from .ocr import populate_text_nodes
from .detect_structure import detect_structures
from .scene_graph import build_scene_graph, promote_component_groups
from .segment import propose_components
from .vectorize_region import vectorize_regions
from .vectorize_stroke import vectorize_strokes


@dataclass(slots=True)
class PipelineArtifacts:
    """Artifact locations produced by a pipeline run."""

    analyze_path: Path
    enhanced_path: Path
    scene_graph_path: Path
    final_svg_path: Path


def run_pipeline(cfg: PipelineConfig) -> PipelineArtifacts:
    """Run the minimal skeleton pipeline and persist protocol artifacts."""

    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_image(cfg.input_path)
    analyze_path = cfg.output_dir / "analyze.json"
    analysis.write_json(analyze_path)

    enhancement = enhance_image(cfg.input_path, analysis, cfg)
    proposal_source, vector_source = _choose_processing_sources(cfg, analysis, enhancement.image_path)

    proposals = propose_components(proposal_source, cfg.output_dir, cfg)
    scene_graph = build_scene_graph(analysis.width, analysis.height, proposals)
    vector_image = _load_vector_image(vector_source)

    # Optimization 6: OCR + vectorize in parallel (vectorize only reads bbox)
    with ThreadPoolExecutor(max_workers=3) as executor:
        ocr_future = executor.submit(populate_text_nodes, vector_image, scene_graph, cfg)
        region_future = executor.submit(vectorize_regions, vector_image, scene_graph.nodes)
        stroke_future = executor.submit(vectorize_strokes, vector_image, scene_graph.nodes)

        scene_graph = ocr_future.result()
        region_results = region_future.result()
        stroke_results = stroke_future.result()

    scene_graph = promote_component_groups(scene_graph)
    scene_graph = detect_structures(scene_graph)
    scene_graph_path = cfg.output_dir / "scene_graph.json"
    scene_graph.write_json(scene_graph_path)
    svg_export = export_svg(
        scene_graph,
        region_results,
        stroke_results,
        cfg.output_dir,
        preview_source_path=enhancement.image_path,
    )

    return PipelineArtifacts(
        analyze_path=analyze_path,
        enhanced_path=enhancement.image_path,
        scene_graph_path=scene_graph_path,
        final_svg_path=svg_export.svg_path,
    )


def _choose_processing_sources(cfg: PipelineConfig, analysis, enhanced_path: Path) -> tuple[Path, Path]:
    if analysis.route_type == "wide_hires":
        return cfg.input_path, cfg.input_path
    if analysis.route_type == "signature_lineart":
        return enhanced_path, enhanced_path
    if analysis.route_type == "small_lowres":
        return enhanced_path, enhanced_path
    return cfg.input_path, enhanced_path


def _load_vector_image(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to load vector source image: {path}")
    return image
