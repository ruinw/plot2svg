"""Top-level pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Callable

import cv2
import numpy as np

from .image_io import read_image, write_image

from .analyze import analyze_image
from .config import PipelineConfig
from .enhance import enhance_image
from .export_svg import export_svg
from .graph_builder import build_graph
from .icon_vectorizer import vectorize_clean_image
from .icon_processor import IconProcessor
from .node_detector import detect_nodes
from .layout_refiner import refine_layout
from .ocr import extract_text_overlays, inpaint_text_nodes
from .detect_structure import detect_structures
from .region_vectorizer import vectorize_region_objects
from .scene_graph import IconObject, RasterObject, RegionObject, SceneGraph, SceneNode, SceneObject, build_object_instances, build_scene_graph, enrich_region_styles, promote_component_groups
from .segment import ComponentProposal, propose_components
from .stroke_detector import detect_strokes
from .svg_templates import append_template_role, infer_template_from_text_context, match_svg_template
from .text_layers import separate_text_graphics, write_text_graphic_layers
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
    """Run the subtraction-style pipeline and persist protocol artifacts."""

    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_image(cfg.input_path)
    analyze_path = cfg.output_dir / "analyze.json"
    analysis.write_json(analyze_path)

    enhancement = enhance_image(cfg.input_path, analysis, cfg)
    proposal_source, _vector_source, _vector_scale = _choose_processing_sources(
        cfg,
        analysis,
        enhancement.image_path,
        enhancement.scale_factor,
    )

    base_image = _load_color_image(proposal_source)
    proposal_layers = separate_text_graphics(base_image)
    write_text_graphic_layers(cfg.output_dir, "proposal", proposal_layers)

    text_nodes = extract_text_overlays(base_image, cfg=cfg)
    text_clean_image, text_mask = inpaint_text_nodes(base_image, text_nodes, padding=6)
    global_ignore_mask = text_mask.copy()
    resolved_graphics_mask = np.zeros_like(global_ignore_mask)
    write_image(cfg.output_dir / 'debug_text_inpaint.png', text_clean_image)

    panel_nodes = _detect_panel_background_nodes(base_image, text_nodes, analysis.width, analysis.height)
    panel_mask = _mask_for_nodes(base_image, panel_nodes, padding=0, artifacts_dir=None)
    global_ignore_mask = _merge_masks(global_ignore_mask, panel_mask)
    resolved_graphics_mask = _merge_masks(resolved_graphics_mask, panel_mask)
    panel_clean_image = _heal_masked_stage_image(base_image, global_ignore_mask, kernel_size=7)
    write_image(cfg.output_dir / 'debug_panels_erased.png', panel_clean_image)
    panel_arrow_nodes, panel_arrow_objects = _detect_panel_arrow_regions(base_image, panel_clean_image, panel_nodes)
    panel_arrow_mask = _mask_for_nodes(base_image, panel_arrow_nodes, padding=2, artifacts_dir=None)
    global_ignore_mask = _merge_masks(global_ignore_mask, panel_arrow_mask)
    resolved_graphics_mask = _merge_masks(resolved_graphics_mask, panel_arrow_mask)

    vector_layers = separate_text_graphics(panel_clean_image)
    write_text_graphic_layers(cfg.output_dir, "vector", vector_layers)

    stage1_graph = enrich_region_styles(
        base_image,
        build_scene_graph(analysis.width, analysis.height, _proposals_for_stage(proposal_layers.graphic_layer, cfg, cfg.output_dir, 'stage1')),
    )
    stage1_graph = _promote_svg_template_nodes(base_image, stage1_graph, text_nodes)
    node_objects = _filter_node_objects(stage1_graph, detect_nodes(text_clean_image, stage1_graph, 1.0))
    raster_objects = _detect_raster_objects(base_image, text_clean_image, stage1_graph, {obj.node_id for obj in node_objects})
    icon_objects, raster_objects = _extract_icon_objects(base_image, stage1_graph, raster_objects)
    icon_cleanup_node_ids = _collect_icon_cleanup_node_ids(stage1_graph, node_objects, raster_objects, icon_objects)

    node_clean_image, node_mask = _inpaint_node_and_icon_regions(
        base_image,
        stage1_graph,
        icon_cleanup_node_ids,
        padding=8,
        artifacts_dir=cfg.output_dir,
        existing_ignore_mask=global_ignore_mask,
    )
    global_ignore_mask = _merge_masks(global_ignore_mask, node_mask)
    resolved_graphics_mask = _merge_masks(resolved_graphics_mask, node_mask)
    write_image(cfg.output_dir / 'debug_nodes_inpaint.png', node_clean_image)

    stage2_layers = separate_text_graphics(node_clean_image)
    stage2_graph = enrich_region_styles(
        base_image,
        build_scene_graph(analysis.width, analysis.height, _proposals_for_stage(stage2_layers.graphic_layer, cfg, cfg.output_dir, 'stage2')),
    )
    stage2_stroke_graph = _filter_stroke_scene_graph(stage2_graph)
    stroke_primitives = detect_strokes(
        stage2_layers.graphic_layer,
        stage2_stroke_graph,
        1.0,
        debug_mask_path=cfg.output_dir / 'debug_lines_mask.png',
    )

    stroke_clean_image, stroke_mask = _inpaint_stroke_regions(
        base_image,
        stage2_stroke_graph,
        padding=5,
        artifacts_dir=cfg.output_dir,
        existing_ignore_mask=global_ignore_mask,
    )
    global_ignore_mask = _merge_masks(global_ignore_mask, stroke_mask)
    resolved_graphics_mask = _merge_masks(resolved_graphics_mask, stroke_mask)
    write_image(cfg.output_dir / 'debug_strokes_inpaint.png', stroke_clean_image)

    stage3_layers = separate_text_graphics(stroke_clean_image)
    stage3_graph = enrich_region_styles(
        base_image,
        build_scene_graph(analysis.width, analysis.height, _proposals_for_stage(stage3_layers.graphic_layer, cfg, cfg.output_dir, None)),
    )

    scene_graph = _assemble_scene_graph(
        analysis.width,
        analysis.height,
        stage1_graph,
        stage2_stroke_graph,
        stage3_graph,
        text_nodes,
        node_objects,
        raster_objects,
        stroke_primitives,
        icon_objects,
    )
    scene_graph = _inject_network_container_object(build_object_instances(scene_graph))
    scene_graph = promote_component_groups(scene_graph)
    scene_graph = detect_structures(scene_graph)
    scene_graph = _inject_fan_relation(scene_graph)
    scene_graph = _attach_panel_background_regions(scene_graph, panel_nodes)
    scene_graph = _attach_synthetic_region_nodes(scene_graph, panel_arrow_nodes)
    scene_graph, raster_objects = _resolve_semantic_raster_objects(base_image, scene_graph, raster_objects)
    container_detail_nodes = _detect_container_detail_regions(base_image, scene_graph, text_mask)
    scene_graph = _attach_synthetic_region_nodes(scene_graph, container_detail_nodes)

    protected_region_ids = (
        {node.id for node in panel_nodes}
        | {node.id for node in panel_arrow_nodes}
        | {obj.node_id for obj in node_objects}
        | {obj.node_id for obj in icon_objects}
        | {obj.node_id for obj in raster_objects}
    )
    scene_graph = _prune_region_nodes_by_mask(
        scene_graph,
        resolved_graphics_mask,
        cfg.output_dir,
        protected_node_ids=protected_region_ids,
    )

    excluded_region_ids = (
        {obj.node_id for obj in node_objects}
        | {obj.node_id for obj in icon_objects}
        | {obj.node_id for obj in raster_objects}
        | {node.id for node in panel_arrow_nodes}
    )
    region_vector_mask = _build_region_vector_ignore_mask(
        text_mask=text_mask,
        node_mask=node_mask,
        stroke_mask=stroke_mask,
        panel_arrow_mask=panel_arrow_mask,
    )
    region_vector_source = _heal_masked_stage_image(base_image, region_vector_mask, kernel_size=7)
    region_objects = vectorize_region_objects(
        region_vector_source,
        scene_graph,
        excluded_node_ids=excluded_region_ids,
        coordinate_scale=1.0,
    )
    region_objects = _filter_region_objects(scene_graph, region_objects, text_nodes)
    region_objects.extend(panel_arrow_objects)
    scene_graph = SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=scene_graph.nodes[:],
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=stroke_primitives,
        node_objects=node_objects,
        region_objects=region_objects,
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=raster_objects,
        graph_edges=scene_graph.graph_edges[:],
    )
    scene_graph = build_graph(scene_graph)
    scene_graph = refine_layout(scene_graph)

    region_results = vectorize_regions(stage3_layers.graphic_layer, scene_graph.nodes, 1.0)
    stroke_results = vectorize_strokes(stage2_layers.graphic_layer, scene_graph.nodes, 1.0)
    scene_graph_path = cfg.output_dir / 'scene_graph.json'
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


def _proposals_for_stage(
    image: np.ndarray,
    cfg: PipelineConfig,
    output_dir: Path,
    stage_prefix: str | None,
) -> list[ComponentProposal]:
    blank_text = np.full_like(image, 255)
    proposals = propose_components(image, output_dir, cfg, text_image_input=blank_text)
    if stage_prefix is None:
        return proposals

    staged_proposals: list[ComponentProposal] = []
    masks_dir = output_dir / 'masks'
    masks_dir.mkdir(parents=True, exist_ok=True)
    for proposal in proposals:
        source_mask_path = output_dir / proposal.mask_path
        staged_mask_name = f'{stage_prefix}-{Path(proposal.mask_path).name}'
        staged_mask_path = masks_dir / staged_mask_name
        if source_mask_path.exists():
            shutil.copyfile(source_mask_path, staged_mask_path)
        staged_proposals.append(
            ComponentProposal(
                component_id=f'{stage_prefix}-{proposal.component_id}',
                bbox=proposal.bbox[:],
                mask_path=f'masks/{staged_mask_name}',
                proposal_type=proposal.proposal_type,
                confidence=proposal.confidence,
                shape_hint=proposal.shape_hint,
            )
        )
    return staged_proposals


def _collect_icon_cleanup_node_ids(
    stage1_graph: SceneGraph,
    node_objects,
    raster_objects: list[RasterObject],
    icon_objects: list[IconObject] | None = None,
) -> set[str]:
    cleanup_ids = {obj.node_id for obj in node_objects} | {obj.node_id for obj in raster_objects}
    cleanup_ids |= {obj.node_id for obj in (icon_objects or [])}
    cleanup_ids |= {
        node.id
        for node in stage1_graph.nodes
        if node.type == 'region' and node.shape_hint == 'svg_template'
    }
    return cleanup_ids


def _assemble_scene_graph(
    width: int,
    height: int,
    stage1_graph: SceneGraph,
    stage2_graph: SceneGraph,
    stage3_graph: SceneGraph,
    text_nodes: list[SceneNode],
    node_objects,
    raster_objects: list[RasterObject],
    stroke_primitives,
    icon_objects: list[IconObject] | None = None,
) -> SceneGraph:
    keep_stage1_ids = (
        {obj.node_id for obj in node_objects}
        | {obj.node_id for obj in (icon_objects or [])}
        | {obj.node_id for obj in raster_objects}
        | {node.id for node in stage1_graph.nodes if node.type == 'region' and node.shape_hint == 'svg_template'}
    )
    preserved_stage1_ids = {
        node.id
        for node in stage1_graph.nodes
        if node.type == 'region'
        and node.id != 'background-root'
        and _is_safe_preserved_region(node, width, height)
        and ((node.shape_hint in {'circle', 'triangle', 'pentagon'}) or _looks_like_container_candidate(node, width, height))
    }
    stage3_regions = [node for node in stage3_graph.nodes if node.type == 'region' and node.id != 'background-root']
    ordered: list[SceneNode] = []
    ordered.extend(node for node in stage3_graph.nodes if node.id == 'background-root')
    ordered.extend(stage3_regions)
    ordered.extend(
        node
        for node in stage1_graph.nodes
        if node.type == 'region'
        and (node.id in keep_stage1_ids or node.id in preserved_stage1_ids)
        and not _overlaps_existing_region(node, stage3_regions)
    )
    ordered.extend(node for node in stage2_graph.nodes if node.type == 'stroke')
    ordered.extend(text_nodes)

    deduped: list[SceneNode] = []
    seen: set[str] = set()
    for index, node in enumerate(ordered):
        if node.id in seen:
            continue
        seen.add(node.id)
        deduped.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=node.component_role,
                children=node.children[:],
                shape_hint=node.shape_hint,
            )
        )
    return SceneGraph(
        width=width,
        height=height,
        nodes=deduped,
        stroke_primitives=stroke_primitives,
        node_objects=list(node_objects),
        icon_objects=list(icon_objects or []),
        raster_objects=raster_objects,
    )


def _overlaps_existing_region(candidate: SceneNode, existing_regions: list[SceneNode]) -> bool:
    for node in existing_regions:
        if _bbox_overlap(candidate.bbox, node.bbox) >= 0.7:
            return True
    return False


def _bbox_overlap(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1)
    return intersection / min(left_area, right_area)


def _bbox_iou(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1)
    union = left_area + right_area - intersection
    return intersection / max(union, 1)


def _looks_like_container_candidate(node: SceneNode, width: int, height: int) -> bool:
    x1, y1, x2, y2 = node.bbox
    area = max(x2 - x1, 1) * max(y2 - y1, 1)
    canvas_area = max(width * height, 1)
    max_dim = max(x2 - x1, y2 - y1)
    return area >= canvas_area * 0.03 or (node.fill_opacity is not None and node.fill_opacity < 0.75 and max_dim >= min(width, height) * 0.18)


def _is_safe_preserved_region(node: SceneNode, width: int, height: int) -> bool:
    if node.shape_hint == 'raster_candidate':
        return False
    return not _looks_like_large_black_artifact(node, width, height)


def _inject_network_container_object(scene_graph: SceneGraph) -> SceneGraph:
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    region_nodes = [node for node in scene_graph.nodes if node.type == 'region' and node.id != 'background-root']
    circle_like = [node for node in region_nodes if node.shape_hint in {'circle', 'triangle', 'pentagon'}]
    stroke_nodes = [node for node in scene_graph.nodes if node.type == 'stroke']
    text_nodes = [node for node in scene_graph.nodes if node.type == 'text' and (node.text_content or '').strip()]

    for region in sorted(region_nodes, key=lambda item: (0 if item.id == 'region-000' else 1, item.bbox[1], -((item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1])))):
        area = max(region.bbox[2] - region.bbox[0], 1) * max(region.bbox[3] - region.bbox[1], 1)
        if area < canvas_area * 0.04:
            continue
        contained_circles = [node for node in circle_like if _contains_bbox(region.bbox, node.bbox, 18)]
        contained_strokes = [node for node in stroke_nodes if _contains_bbox(region.bbox, node.bbox, 18)]
        contained_text = [node for node in text_nodes if _contains_bbox(region.bbox, node.bbox, 18)]
        total_contained = len(contained_circles) + len(contained_strokes) + len(contained_text)
        if total_contained < 3 and len(contained_circles) < 2 and len(contained_strokes) < 2:
            continue
        node_ids = [region.id] + [node.id for node in contained_circles] + [node.id for node in contained_strokes] + [node.id for node in contained_text]
        objects = scene_graph.objects[:] + [
            SceneObject(
                id=f'object-{region.id}-network',
                object_type='network_container',
                bbox=region.bbox[:],
                node_ids=node_ids,
                metadata={
                    'source': 'pipeline',
                    'contained_count': len(node_ids) - 1,
                    'circle_count': len(contained_circles),
                    'stroke_count': len(contained_strokes),
                },
            )
        ]
        return SceneGraph(
            width=scene_graph.width,
            height=scene_graph.height,
            nodes=scene_graph.nodes[:],
            groups=scene_graph.groups[:],
            relations=scene_graph.relations[:],
            objects=objects,
            stroke_primitives=scene_graph.stroke_primitives[:],
            node_objects=scene_graph.node_objects[:],
            region_objects=scene_graph.region_objects[:],
            icon_objects=scene_graph.icon_objects[:],
            raster_objects=scene_graph.raster_objects[:],
            graph_edges=scene_graph.graph_edges[:],
        )
    return scene_graph


def _contains_bbox(outer: list[int], inner: list[int], margin: int) -> bool:
    return (
        outer[0] - margin <= inner[0]
        and outer[1] - margin <= inner[1]
        and outer[2] + margin >= inner[2]
        and outer[3] + margin >= inner[3]
    )


def _inject_fan_relation(scene_graph: SceneGraph) -> SceneGraph:
    if any(relation.relation_type == 'fan' for relation in scene_graph.relations):
        return scene_graph

    circle_nodes = [
        node for node in scene_graph.nodes
        if node.type == 'region' and node.shape_hint == 'circle' and node.bbox[0] <= scene_graph.width * 0.18
    ]
    if len(circle_nodes) < 4:
        return scene_graph
    circle_nodes = sorted(circle_nodes, key=lambda item: item.bbox[1])
    span_top = circle_nodes[0].bbox[1]
    span_bottom = circle_nodes[-1].bbox[3]
    target = next(
        (
            node for node in scene_graph.nodes
            if node.type == 'region'
            and node.shape_hint != 'circle'
            and node.id != 'background-root'
            and node.bbox[0] > scene_graph.width * 0.12
            and node.bbox[1] <= span_bottom
            and node.bbox[3] >= span_top
        ),
        None,
    )
    if target is None:
        return scene_graph
    stroke = next(
        (
            node for node in scene_graph.nodes
            if node.type == 'stroke'
            and node.bbox[0] <= scene_graph.width * 0.25
            and (node.bbox[3] - node.bbox[1]) >= 140
        ),
        None,
    )
    child_ids = [node.id for node in circle_nodes[: min(len(circle_nodes), 6)]] + [target.id]
    if stroke is not None:
        child_ids.insert(0, stroke.id)
    bbox = [
        min(node.bbox[0] for node in scene_graph.nodes if node.id in child_ids),
        min(node.bbox[1] for node in scene_graph.nodes if node.id in child_ids),
        max(node.bbox[2] for node in scene_graph.nodes if node.id in child_ids),
        max(node.bbox[3] for node in scene_graph.nodes if node.id in child_ids),
    ]
    from .scene_graph import SceneGroup, SceneRelation
    groups = scene_graph.groups[:] + [
        SceneGroup(
            id='fan-synthetic-0',
            role='fan',
            bbox=bbox,
            child_ids=child_ids,
            shape_type='fan',
            direction='right',
        )
    ]
    relations = scene_graph.relations[:] + [
        SceneRelation(
            id='relation-fan-synthetic-0',
            relation_type='fan',
            source_ids=[node.id for node in circle_nodes[: min(len(circle_nodes), 6)]],
            target_ids=[target.id],
            backbone_id=stroke.id if stroke is not None else None,
            group_id='fan-synthetic-0',
            metadata={'direction': 'right', 'source': 'pipeline'},
        )
    ]
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=scene_graph.nodes[:],
        groups=groups,
        relations=relations,
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _inject_panel_background_regions(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    text_nodes: list[SceneNode],
) -> SceneGraph:
    panel_nodes = _detect_panel_background_nodes(
        source_image,
        text_nodes,
        scene_graph.width,
        scene_graph.height,
        existing_nodes=scene_graph.nodes,
    )
    return _attach_panel_background_regions(scene_graph, panel_nodes)


def _detect_panel_background_nodes(
    source_image: np.ndarray,
    text_nodes: list[SceneNode],
    width: int,
    height: int,
    existing_nodes: list[SceneNode] | None = None,
) -> list[SceneNode]:
    existing_nodes = existing_nodes or []
    if any(node.id.startswith('panel-region-') for node in existing_nodes):
        return []

    canvas_area = max(width * height, 1)
    existing_large_regions = [
        node
        for node in existing_nodes
        if node.type == 'region'
        and node.id != 'background-root'
        and (node.bbox[2] - node.bbox[0]) * (node.bbox[3] - node.bbox[1]) >= canvas_area * 0.05
    ]
    if len(existing_large_regions) >= 2:
        return []

    column_groups = _cluster_text_columns(text_nodes, width)
    if len(column_groups) < 3:
        return []

    boundaries = [0]
    for left_group, right_group in zip(column_groups, column_groups[1:]):
        boundaries.append(int(round((left_group[1] + right_group[0]) / 2.0)))
    boundaries.append(width)

    visible_text = [node for node in text_nodes if (node.text_content or '').strip()]
    if not visible_text:
        return []
    top = max(min(node.bbox[1] for node in visible_text) - 28, 0)
    bottom = min(max(node.bbox[3] for node in visible_text) + 28, height)
    if (bottom - top) * width < canvas_area * 0.2:
        return []

    blurred = cv2.GaussianBlur(source_image, (101, 101), 0)
    panel_nodes: list[SceneNode] = []
    for index, (x1, x2) in enumerate(zip(boundaries, boundaries[1:])):
        bbox = [max(x1, 0), top, min(x2, width), bottom]
        if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < canvas_area * 0.05:
            continue
        fill = _sample_panel_fill(blurred, bbox)
        if fill is None or _is_near_white(fill):
            continue
        panel_nodes.append(
            SceneNode(
                id=f'panel-region-{index:03d}',
                type='region',
                bbox=bbox,
                z_index=index + 1,
                vector_mode='region_path',
                confidence=0.99,
                fill=fill,
                fill_opacity=0.92,
                stroke=fill,
                shape_hint='panel',
            )
        )
    if len(panel_nodes) < 3:
        return []
    return panel_nodes


def _attach_panel_background_regions(
    scene_graph: SceneGraph,
    panel_nodes: list[SceneNode],
) -> SceneGraph:
    if not panel_nodes:
        return scene_graph
    if any(node.id.startswith('panel-region-') for node in scene_graph.nodes):
        return scene_graph

    background_nodes = [node for node in scene_graph.nodes if node.id == 'background-root']
    other_nodes = [node for node in scene_graph.nodes if node.id != 'background-root']
    reordered_nodes: list[SceneNode] = []
    for index, node in enumerate([*background_nodes, *panel_nodes, *other_nodes]):
        reordered_nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=node.component_role,
                children=node.children[:],
                shape_hint=node.shape_hint,
            )
        )

    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=reordered_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )



def _attach_synthetic_region_nodes(
    scene_graph: SceneGraph,
    nodes: list[SceneNode],
) -> SceneGraph:
    if not nodes:
        return scene_graph
    existing_ids = {node.id for node in scene_graph.nodes}
    synthetic_nodes = [node for node in nodes if node.id not in existing_ids]
    if not synthetic_nodes:
        return scene_graph

    background_nodes = [node for node in scene_graph.nodes if node.id == 'background-root']
    body_nodes = [node for node in scene_graph.nodes if node.id != 'background-root' and node.type != 'text']
    text_nodes = [node for node in scene_graph.nodes if node.type == 'text']
    ordered_nodes = [*background_nodes, *body_nodes, *synthetic_nodes, *text_nodes]
    rebuilt_nodes: list[SceneNode] = []
    for index, node in enumerate(ordered_nodes):
        rebuilt_nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=node.component_role,
                children=node.children[:],
                shape_hint=node.shape_hint,
            )
        )
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=rebuilt_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )



def _detect_container_detail_regions(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    text_mask: np.ndarray | None,
) -> list[SceneNode]:
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    existing_regions = [node for node in scene_graph.nodes if node.type == 'region']
    detail_nodes: list[SceneNode] = []
    detail_index = 0

    for node in existing_regions:
        if node.id == 'background-root':
            continue
        if node.shape_hint in {'panel', 'panel_arrow', 'circle', 'triangle', 'pentagon', 'svg_template'}:
            continue
        component_role = str(node.component_role or '')
        group_id = str(node.group_id or '')
        if 'container_shape' not in component_role and 'container_boundary' not in component_role and not group_id.startswith('component-text-overlay-'):
            continue

        x1, y1, x2, y2 = _clamp_bbox(node.bbox, scene_graph.width, scene_graph.height)
        width = max(x2 - x1, 1)
        height = max(y2 - y1, 1)
        bbox_area = width * height
        if bbox_area < canvas_area * 0.02:
            continue

        contained_text = [
            text_node
            for text_node in scene_graph.nodes
            if text_node.type == 'text'
            and (text_node.text_content or '').strip()
            and _contains_bbox(node.bbox, text_node.bbox, 12)
        ]
        if len(contained_text) < 4:
            continue

        crop = source_image[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        local_text_mask = text_mask[y1:y2, x1:x2] if text_mask is not None and text_mask.size > 0 else np.zeros((height, width), dtype=np.uint8)
        background_bgr = _hex_to_bgr(node.fill)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        if background_bgr is not None:
            color_delta = np.max(np.abs(crop.astype(np.int16) - np.array(background_bgr, dtype=np.int16)), axis=2)
        else:
            color_delta = 255 - gray.astype(np.int16)

        detail_mask = np.where(
            (((color_delta >= 28) & (gray < 245)) | ((hsv[:, :, 1] >= 40) & (gray < 240)) | (gray < 170))
            & (local_text_mask == 0),
            255,
            0,
        ).astype(np.uint8)
        if not np.any(detail_mask):
            continue

        detail_mask = cv2.morphologyEx(detail_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        detail_mask = cv2.morphologyEx(detail_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(detail_mask, connectivity=8)
        for label in range(1, num_labels):
            lx, ly, lw, lh, area = stats[label]
            if area < 60:
                continue
            if lw < 6 or lh < 6:
                continue
            if area > bbox_area * 0.18:
                continue
            fill_ratio = area / max(lw * lh, 1)
            if fill_ratio < 0.12:
                continue
            local_bbox = [int(lx), int(ly), int(lx + lw), int(ly + lh)]
            if _bbox_overlap(local_bbox, [0, 0, width, height]) >= 0.98 and area >= bbox_area * 0.35:
                continue
            if lx <= 1 and ly <= 1 and lx + lw >= width - 1 and ly + lh >= height - 1:
                continue

            global_bbox = [x1 + int(lx), y1 + int(ly), x1 + int(lx + lw), y1 + int(ly + lh)]
            if any(
                other.id != node.id
                and other.type == 'region'
                and other.shape_hint not in {'panel', 'panel_arrow'}
                and 'container' not in str(other.component_role or '')
                and _bbox_overlap(global_bbox, other.bbox) >= 0.78
                for other in existing_regions
            ):
                continue

            component_pixels = crop[labels == label]
            if component_pixels.size == 0:
                continue
            dominant = np.median(component_pixels, axis=0).astype(np.uint8)
            fill = _bgr_to_hex((int(dominant[0]), int(dominant[1]), int(dominant[2])))
            if fill == (node.fill or '').lower():
                continue
            if _is_near_black(fill):
                continue
            channel_spread = int(np.max(dominant)) - int(np.min(dominant))
            dominant_hsv = cv2.cvtColor(dominant.reshape(1, 1, 3), cv2.COLOR_BGR2HSV)[0, 0]
            if channel_spread < 18 and int(np.max(dominant)) < 180:
                continue
            if int(dominant_hsv[1]) < 22 and area < 900:
                continue

            detail_nodes.append(
                SceneNode(
                    id=f'container-detail-region-{detail_index:03d}',
                    type='region',
                    bbox=global_bbox,
                    z_index=0,
                    vector_mode='region_path',
                    confidence=0.86,
                    fill=fill,
                    fill_opacity=0.95,
                    stroke=fill,
                    group_id=node.group_id,
                    component_role='detail_region',
                    shape_hint='vector_candidate',
                )
            )
            detail_index += 1
    return detail_nodes


def _detect_panel_arrow_regions(
    source_image: np.ndarray,
    working_image: np.ndarray,
    panel_nodes: list[SceneNode],
) -> tuple[list[SceneNode], list[RegionObject]]:
    ordered_panels = sorted(panel_nodes, key=lambda item: item.bbox[0])
    if len(ordered_panels) < 2:
        return [], []

    visible_boxes = [_estimate_visible_panel_bbox(source_image, node) for node in ordered_panels]
    border_colors = [_sample_panel_border_color(source_image, bbox) for bbox in visible_boxes[:-1]]
    border_mask = np.zeros(working_image.shape[:2], dtype=np.uint8)
    for x1, y1, x2, y2 in visible_boxes:
        cv2.rectangle(border_mask, (x1, y1), (x2 - 1, y2 - 1), 255, 8)

    hsv = cv2.cvtColor(working_image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(working_image, cv2.COLOR_BGR2GRAY)
    base_mask = np.where((hsv[:, :, 1] > 35) & (gray < 220) & (border_mask == 0), 255, 0).astype(np.uint8)
    base_mask = cv2.morphologyEx(base_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    base_mask = cv2.morphologyEx(base_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    arrow_nodes: list[SceneNode] = []
    arrow_objects: list[RegionObject] = []
    image_height, image_width = working_image.shape[:2]
    for index, (left_box, right_box, border_color) in enumerate(zip(visible_boxes, visible_boxes[1:], border_colors)):
        if border_color is None:
            continue
        boundary = left_box[2]
        search_x1 = max(boundary - 80, 0)
        search_x2 = min(boundary + 80, image_width)
        search_y1 = max(min(left_box[1], right_box[1]) + 120, 0)
        search_y2 = min(int(image_height * 0.60), image_height)
        if search_y2 <= search_y1:
            continue
        crop = base_mask[search_y1:search_y2, search_x1:search_x2]
        if crop.size == 0:
            continue

        candidate_boxes = _collect_boundary_arrow_boxes(crop, boundary, search_x1, search_y1)
        selected_boxes = _select_boundary_arrow_boxes(candidate_boxes, boundary)
        for local_index, bbox in enumerate(selected_boxes):
            fill = _sample_arrow_fill_color(source_image, bbox, border_color)
            node_bbox, path = _synthesize_right_arrow_path(bbox, right_box[0])
            node_id = f'panel-arrow-region-{index:02d}-{local_index:02d}'
            arrow_nodes.append(
                SceneNode(
                    id=node_id,
                    type='region',
                    bbox=node_bbox,
                    z_index=0,
                    vector_mode='region_path',
                    confidence=0.96,
                    fill=fill,
                    fill_opacity=0.98,
                    stroke=fill,
                    shape_hint='panel_arrow',
                )
            )
            arrow_objects.append(
                RegionObject(
                    id=f'region-object-{node_id}',
                    node_id=node_id,
                    outer_path=path,
                    holes=[],
                    fill=fill,
                    fill_opacity=0.98,
                    stroke=fill,
                    metadata={
                        'shape_type': 'panel_arrow_template',
                        'synthetic': True,
                        'orientation': 'right',
                        'template_bbox': node_bbox,
                    },
                )
            )
    return arrow_nodes, arrow_objects


def _estimate_visible_panel_bbox(source_image: np.ndarray, node: SceneNode) -> list[int]:
    target_bgr = _hex_to_bgr(node.fill)
    if target_bgr is None:
        return node.bbox[:]
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, source_image.shape[1], source_image.shape[0])
    crop = source_image[y1:y2, x1:x2].astype(np.int16)
    if crop.size == 0:
        return node.bbox[:]
    gray = cv2.cvtColor(source_image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    delta = np.max(np.abs(crop - np.array(target_bgr, dtype=np.int16)), axis=2)
    mask = np.where((delta <= 24) & (gray >= 170), 255, 0).astype(np.uint8)
    points = cv2.findNonZero(mask)
    if points is None:
        return node.bbox[:]
    rx, ry, width, height = cv2.boundingRect(points)
    return [x1 + int(rx), y1 + int(ry), x1 + int(rx + width), y1 + int(ry + height)]


def _sample_panel_border_color(source_image: np.ndarray, bbox: list[int]) -> tuple[int, int, int] | None:
    x1, y1, x2, y2 = _clamp_bbox(bbox, source_image.shape[1], source_image.shape[0])
    border_mask = np.zeros(source_image.shape[:2], dtype=np.uint8)
    cv2.rectangle(border_mask, (x1, y1), (x2 - 1, y2 - 1), 255, 8)
    pixels = source_image[border_mask > 0]
    if pixels.size == 0:
        return None
    hsv_pixels = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    saturated = pixels[(hsv_pixels[:, 1] > 35) & (pixels.max(axis=1) < 240)]
    if saturated.size == 0:
        return None
    quantized = np.clip(((saturated.astype(np.int32) + 8) // 16) * 16, 0, 255)
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    return int(dominant[0]), int(dominant[1]), int(dominant[2])


def _collect_boundary_arrow_boxes(
    crop_mask: np.ndarray,
    boundary: int,
    offset_x: int,
    offset_y: int,
) -> list[list[int]]:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(crop_mask, connectivity=8)
    boxes: list[list[int]] = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area < 100:
            continue
        global_bbox = [offset_x + int(x), offset_y + int(y), offset_x + int(x + width), offset_y + int(y + height)]
        if global_bbox[2] < boundary - 25 or global_bbox[0] > boundary + 70:
            continue
        if width > 120 or height > 120:
            continue
        boxes.append(global_bbox)
    return _merge_nearby_bboxes(boxes)


def _merge_nearby_bboxes(boxes: list[list[int]]) -> list[list[int]]:
    merged = [box[:] for box in boxes]
    changed = True
    while changed:
        changed = False
        next_boxes: list[list[int]] = []
        while merged:
            current = merged.pop(0)
            merged_current = False
            for index, other in enumerate(merged):
                vertical_overlap = min(current[3], other[3]) - max(current[1], other[1])
                horizontal_gap = max(other[0] - current[2], current[0] - other[2], 0)
                if vertical_overlap >= min(current[3] - current[1], other[3] - other[1]) * 0.4 and horizontal_gap <= 18:
                    current = [
                        min(current[0], other[0]),
                        min(current[1], other[1]),
                        max(current[2], other[2]),
                        max(current[3], other[3]),
                    ]
                    merged.pop(index)
                    changed = True
                    merged_current = True
                    break
            if merged_current:
                merged.insert(0, current)
                continue
            next_boxes.append(current)
        merged = next_boxes
    return merged


def _select_boundary_arrow_boxes(boxes: list[list[int]], boundary: int) -> list[list[int]]:
    if not boxes:
        return []
    ranked = sorted(boxes, key=lambda item: ((item[2] - item[0]) * (item[3] - item[1])), reverse=True)
    selected: list[list[int]] = []
    wide_candidate = next(
        (
            box for box in ranked
            if (box[2] - box[0]) >= 28 and (box[3] - box[1]) <= 48 and box[1] <= 260
        ),
        None,
    )
    if wide_candidate is not None:
        selected.append(wide_candidate)
    tall_candidate = next(
        (
            box for box in ranked
            if (box[3] - box[1]) >= 30 and (box[2] - box[0]) <= 24 and box[0] <= boundary + 24
        ),
        None,
    )
    if tall_candidate is not None and all(_bbox_overlap(tall_candidate, current) < 0.3 for current in selected):
        selected.append(tall_candidate)
    if not selected and ranked:
        selected.append(ranked[0])
    return selected


def _sample_arrow_fill_color(image: np.ndarray, bbox: list[int], fallback_color: tuple[int, int, int]) -> str:
    x1, y1, x2, y2 = _clamp_bbox(bbox, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return _bgr_to_hex(fallback_color)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = (hsv[:, :, 1] > 35) & (gray < 220)
    if not np.any(mask):
        return _bgr_to_hex(fallback_color)
    pixels = crop[mask].reshape(-1, 3)
    quantized = ((pixels.astype(np.int32) + 8) // 16) * 16
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    return _bgr_to_hex((int(dominant[0]), int(dominant[1]), int(dominant[2])))


def _synthesize_right_arrow_path(bbox: list[int], next_panel_left: int) -> tuple[list[int], str]:
    x1, y1, x2, y2 = bbox
    height = max(y2 - y1, 1)
    width = max(x2 - x1, 1)
    head_width = max(min(int(height * 0.9), 40), 16)
    if width >= 28:
        body_x2 = x2
        tip_x = min(x2 + max(head_width // 2, 10), next_panel_left + 42)
    else:
        body_x2 = x2
        tip_x = min(x2 + head_width, next_panel_left + 42)
    mid_y = (y1 + y2) // 2
    path = (
        f'M {x1} {y1} '
        f'L {body_x2} {y1} '
        f'L {tip_x} {mid_y} '
        f'L {body_x2} {y2} '
        f'L {x1} {y2} Z'
    )
    return [x1, y1, tip_x, y2], path


def _bgr_to_hex(color: tuple[int, int, int]) -> str:
    b, g, r = color
    return f'#{r:02x}{g:02x}{b:02x}'


def _cluster_text_columns(text_nodes: list[SceneNode], width: int) -> list[tuple[int, int]]:
    intervals = sorted(
        [
            (node.bbox[0], node.bbox[2])
            for node in text_nodes
            if (node.text_content or '').strip()
        ],
        key=lambda item: item[0],
    )
    if not intervals:
        return []

    gap_threshold = max(24, int(width * 0.015))
    clusters: list[list[int]] = []
    for x1, x2 in intervals:
        if not clusters or x1 > clusters[-1][1] + gap_threshold:
            clusters.append([x1, x2])
        else:
            clusters[-1][1] = max(clusters[-1][1], x2)
    return [(x1, x2) for x1, x2 in clusters if (x2 - x1) >= max(60, int(width * 0.08))]


def _sample_panel_fill(image: np.ndarray, bbox: list[int]) -> str | None:
    x1, y1, x2, y2 = _clamp_bbox(bbox, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = (gray < 245) | (hsv[:, :, 1] > 12)
    if not np.any(mask):
        return None
    pixels = crop[mask].reshape(-1, 3)
    quantized = ((pixels.astype(np.int32) + 8) // 16) * 16
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    b, g, r = [int(np.clip(channel, 0, 255)) for channel in dominant]
    return f'#{r:02x}{g:02x}{b:02x}'



def _hex_to_bgr(color: str | None) -> tuple[int, int, int] | None:
    if color is None or not color.startswith('#') or len(color) != 7:
        return None
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return None
    return b, g, r


def _is_near_white(color: str | None) -> bool:
    if color is None or not color.startswith('#') or len(color) != 7:
        return False
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return False
    return min(r, g, b) >= 236


def _filter_node_objects(scene_graph: SceneGraph, node_objects) -> list:
    filtered = []
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    node_map = {node.id: node for node in scene_graph.nodes}
    for node_obj in node_objects:
        source_node = node_map.get(node_obj.node_id)
        if source_node is None:
            filtered.append(node_obj)
            continue
        if source_node.shape_hint == 'raster_candidate':
            continue
        x1, y1, x2, y2 = source_node.bbox
        area = max(x2 - x1, 1) * max(y2 - y1, 1)
        max_dim = max(x2 - x1, y2 - y1)
        if area > canvas_area * 0.03:
            continue
        if max_dim > min(scene_graph.width, scene_graph.height) * 0.18:
            continue
        if _looks_like_large_black_artifact(source_node, scene_graph.width, scene_graph.height):
            continue
        filtered.append(node_obj)
    return filtered





def _should_route_template_candidate_to_icon_object(
    template_name: str,
    crop: np.ndarray,
    complexity,
) -> bool:
    vectorized = vectorize_clean_image(crop)
    if vectorized is None:
        return False

    max_side = max(crop.shape[:2])
    area = crop.shape[0] * crop.shape[1]
    path_count = vectorized.compound_path.count('M ')

    if template_name == 'document':
        if max_side < 48:
            return False
        if getattr(complexity, 'variance', 0.0) < 1200.0:
            return False
        return vectorized.inner_count >= 4 and (vectorized.outer_count >= 2 or path_count >= 8)

    if template_name in {'database', 'clock'}:
        if max_side < 64 or area < 2500:
            return False
        return vectorized.inner_count >= 12 and path_count >= 18

    return False


def _promote_svg_template_nodes(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    text_nodes: list[SceneNode] | None = None,
) -> SceneGraph:
    processor = IconProcessor()
    updated_nodes: list[SceneNode] = []
    changed = False
    for node in scene_graph.nodes:
        if node.type != 'region' or node.shape_hint != 'raster_candidate':
            updated_nodes.append(node)
            continue
        if not _is_template_candidate_bbox(node.bbox):
            changed = True
            updated_nodes.append(
                SceneNode(
                    id=node.id,
                    type=node.type,
                    bbox=node.bbox[:],
                    z_index=node.z_index,
                    vector_mode=node.vector_mode,
                    confidence=node.confidence,
                    fill=node.fill,
                    fill_opacity=node.fill_opacity,
                    stroke=node.stroke,
                    stroke_width=node.stroke_width,
                    source_mask=node.source_mask,
                    text_content=node.text_content,
                    group_id=node.group_id,
                    component_role=node.component_role,
                    children=node.children[:],
                    shape_hint='vector_candidate',
                )
            )
            continue
        x1, y1, x2, y2 = _clamp_bbox(node.bbox, scene_graph.width, scene_graph.height)
        crop = source_image[y1:y2, x1:x2]
        if crop.size == 0:
            updated_nodes.append(node)
            continue
        complexity = processor.evaluate_complexity(crop)
        template_name = infer_template_from_text_context(_text_context_near_bbox(text_nodes or [], node.bbox))
        if not template_name:
            template_name = match_svg_template(crop, complexity)
        if not template_name:
            updated_nodes.append(node)
            continue
        if _should_route_template_candidate_to_icon_object(template_name, crop, complexity):
            changed = True
            component_role = append_template_role(node.component_role, template_name)
            if 'icon_candidate' not in component_role.split('|'):
                component_role = f"{component_role}|icon_candidate"
            updated_nodes.append(
                SceneNode(
                    id=node.id,
                    type=node.type,
                    bbox=node.bbox[:],
                    z_index=node.z_index,
                    vector_mode=node.vector_mode,
                    confidence=node.confidence,
                    fill=node.fill,
                    fill_opacity=node.fill_opacity,
                    stroke=node.stroke,
                    stroke_width=node.stroke_width,
                    source_mask=node.source_mask,
                    text_content=node.text_content,
                    group_id=node.group_id,
                    component_role=component_role,
                    children=node.children[:],
                    shape_hint='raster_candidate',
                )
            )
            continue
        changed = True
        updated_nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=node.z_index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=append_template_role(node.component_role, template_name),
                children=node.children[:],
                shape_hint='svg_template',
            )
        )
    if not changed:
        return scene_graph
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=updated_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


_ICON_PATH_COORDINATE_RE = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


def _extract_icon_objects(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    raster_objects: list[RasterObject],
) -> tuple[list[IconObject], list[RasterObject]]:
    if not raster_objects:
        return [], []

    node_map = {node.id: node for node in scene_graph.nodes}
    icon_objects: list[IconObject] = []
    kept_rasters: list[RasterObject] = []
    for raster_obj in raster_objects:
        node = node_map.get(raster_obj.node_id)
        shape_hint = str((raster_obj.metadata or {}).get('shape_hint') or (node.shape_hint if node is not None else ''))
        if shape_hint not in {'raster_candidate', 'icon_cluster'}:
            kept_rasters.append(raster_obj)
            continue
        x1, y1, x2, y2 = _clamp_bbox(raster_obj.bbox, scene_graph.width, scene_graph.height)
        crop = source_image[y1:y2, x1:x2]
        if crop.size == 0:
            kept_rasters.append(raster_obj)
            continue
        vectorized = vectorize_clean_image(crop)
        if vectorized is None or vectorized.inner_count <= 0:
            kept_rasters.append(raster_obj)
            continue
        fill = '#111111'
        if node is not None and node.fill and node.fill.lower() not in {'none', '#ffffff', 'white'}:
            fill = node.fill
        elif isinstance((raster_obj.metadata or {}).get('fill'), str) and str((raster_obj.metadata or {}).get('fill')).strip():
            fill = str((raster_obj.metadata or {}).get('fill'))
        icon_objects.append(
            IconObject(
                id=f'icon-{raster_obj.id}',
                node_id=raster_obj.node_id,
                bbox=raster_obj.bbox[:],
                compound_path=_translate_compound_path(vectorized.compound_path, x1, y1),
                fill=fill,
                fill_rule='evenodd',
                metadata={
                    **(raster_obj.metadata or {}),
                    'source': 'icon_vectorizer',
                    'outer_count': vectorized.outer_count,
                    'inner_count': vectorized.inner_count,
                },
            )
        )
    return icon_objects, kept_rasters


def _translate_compound_path(path_data: str, offset_x: int, offset_y: int) -> str:
    def repl(match: re.Match[str]) -> str:
        x = float(match.group(1)) + offset_x
        y = float(match.group(2)) + offset_y
        return f'{x:.0f},{y:.0f}'

    return _ICON_PATH_COORDINATE_RE.sub(repl, path_data)


def _detect_raster_objects(
    source_image: np.ndarray,
    working_image: np.ndarray,
    scene_graph: SceneGraph,
    excluded_node_ids: set[str],
) -> list[RasterObject]:
    raster_objects: list[RasterObject] = []
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    processor = IconProcessor()
    for node in scene_graph.nodes:
        if node.type != 'region' or node.id == 'background-root' or node.id in excluded_node_ids:
            continue
        if node.shape_hint in {'circle', 'triangle', 'pentagon'}:
            continue
        x1, y1, x2, y2 = _clamp_bbox(node.bbox, scene_graph.width, scene_graph.height)
        width = x2 - x1
        height = y2 - y1
        area = width * height
        component_role = str(node.component_role or '')
        is_icon_candidate = 'icon_candidate' in component_role.split('|')
        forced_raster = node.shape_hint in {'raster_candidate', 'icon_cluster'}
        if node.shape_hint == 'svg_template':
            continue
        if width < 24 or height < 24:
            continue
        if area > canvas_area * 0.18 and not is_icon_candidate and not forced_raster:
            continue

        source_crop = source_image[y1:y2, x1:x2]
        work_crop = working_image[y1:y2, x1:x2]
        if source_crop.size == 0 or work_crop.size == 0:
            continue

        complexity = processor.evaluate_complexity(source_crop)
        if not forced_raster and not complexity.is_complex:
            continue

        try:
            image_href = processor.encode_image_href(source_crop)
        except RuntimeError:
            continue
        raster_objects.append(
            RasterObject(
                id=f'raster-{node.id}',
                node_id=node.id,
                bbox=[x1, y1, x2, y2],
                image_href=image_href,
                metadata={
                    'source': 'pipeline',
                    'shape_hint': node.shape_hint,
                    'contours': complexity.contour_count,
                    'significant_colors': complexity.significant_colors,
                    'variance': round(complexity.variance, 3),
                },
            )
        )
    return raster_objects


_CHART_TEXT_KEYWORDS = (
    'auc',
    'kaplan',
    'survival curve',
    'survival curves',
    'bar chart',
    'c-index metric',
    'importance',
)


def _resolve_semantic_raster_objects(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    raster_objects: list[RasterObject],
) -> tuple[SceneGraph, list[RasterObject]]:
    if not raster_objects:
        return scene_graph, raster_objects

    text_nodes = [node for node in scene_graph.nodes if node.type == 'text' and (node.text_content or '').strip()]
    node_map = {node.id: node for node in scene_graph.nodes}
    kept_rasters: list[RasterObject] = []
    semantic_updates: dict[str, tuple[str, str | None]] = {}
    processor = IconProcessor()

    for raster_obj in raster_objects:
        node = node_map.get(raster_obj.node_id)
        if node is None:
            continue
        if not _is_template_candidate_bbox(raster_obj.bbox):
            semantic_updates[node.id] = ('vector_candidate', None)
            continue

        x1, y1, x2, y2 = _clamp_bbox(raster_obj.bbox, scene_graph.width, scene_graph.height)
        crop = source_image[y1:y2, x1:x2]
        if crop.size == 0:
            semantic_updates[node.id] = ('vector_candidate', None)
            continue

        complexity = processor.evaluate_complexity(crop)
        text_content = _text_context_near_bbox(text_nodes, raster_obj.bbox)
        if not text_content:
            text_content = ' '.join(_texts_within_bbox(text_nodes, raster_obj.bbox)).lower()
        if _looks_like_data_chart(text_content):
            semantic_updates[node.id] = ('data_chart', None)
            kept_rasters.append(
                RasterObject(
                    id=raster_obj.id,
                    node_id=raster_obj.node_id,
                    bbox=raster_obj.bbox[:],
                    image_href=raster_obj.image_href,
                    metadata={**raster_obj.metadata, 'semantic_label': 'data_chart', 'shape_hint': 'data_chart'},
                )
            )
            continue

        template_name = infer_template_from_text_context(text_content)
        if not template_name:
            template_name = match_svg_template(crop, complexity)
        if template_name:
            semantic_updates[node.id] = ('svg_template', template_name)
            continue

        semantic_updates[node.id] = ('vector_candidate', None)

    updated_nodes: list[SceneNode] = []
    for node in scene_graph.nodes:
        update = semantic_updates.get(node.id)
        if update is None:
            updated_nodes.append(node)
            continue
        shape_hint, template_name = update
        component_role = _append_component_role_tag(node.component_role, 'semantic_recovered')
        if shape_hint == 'svg_template' and template_name:
            component_role = append_template_role(component_role, template_name)
        updated_nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=node.z_index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=component_role,
                children=node.children[:],
                shape_hint=shape_hint,
            )
        )

    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=updated_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=kept_rasters,
        graph_edges=scene_graph.graph_edges[:],
    ), kept_rasters



def _append_component_role_tag(component_role: str | None, tag: str) -> str:
    role = str(component_role or '').strip()
    parts = [part for part in role.split() if part]
    if tag not in parts:
        parts.append(tag)
    return ' '.join(parts)


def _is_template_candidate_bbox(bbox: list[int]) -> bool:
    x1, y1, x2, y2 = bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    area = width * height
    if 400 <= area <= 25000 and max(width, height) <= 180:
        return True
    aspect_ratio = max(width, height) / max(min(width, height), 1)
    return (
        4000 <= area <= 90000
        and height >= 160
        and width >= 60
        and width <= 260
        and aspect_ratio >= 2.0
    )


def _texts_within_bbox(text_nodes: list[SceneNode], bbox: list[int]) -> list[str]:
    matches: list[str] = []
    for text_node in text_nodes:
        if _bbox_iou(bbox, text_node.bbox) >= 0.8 or _contains_bbox(bbox, text_node.bbox, 10):
            text = (text_node.text_content or '').strip()
            if text:
                matches.append(text)
    return matches


def _text_context_near_bbox(text_nodes: list[SceneNode], bbox: list[int]) -> str:
    x1, y1, x2, y2 = bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    limit = max(64, int(max(width, height) * 0.6))
    nearby: list[str] = []
    for text_node in text_nodes:
        text = (text_node.text_content or '').strip()
        if not text:
            continue
        if _bbox_gap(bbox, text_node.bbox) <= limit:
            nearby.append(text.lower())
    return ' '.join(nearby)


def _bbox_gap(left: list[int], right: list[int]) -> int:
    horizontal_gap = max(left[0] - right[2], right[0] - left[2], 0)
    vertical_gap = max(left[1] - right[3], right[1] - left[3], 0)
    return max(horizontal_gap, vertical_gap)


def _looks_like_data_chart(text_content: str) -> bool:
    lowered = text_content.lower()
    return any(keyword in lowered for keyword in _CHART_TEXT_KEYWORDS)


def _merge_masks(*masks: np.ndarray | None) -> np.ndarray:
    available = [mask for mask in masks if mask is not None and mask.size > 0]
    if not available:
        return np.zeros((0, 0), dtype=np.uint8)

    merged = np.zeros_like(available[0], dtype=np.uint8)
    for mask in available:
        merged = cv2.bitwise_or(merged, np.where(mask > 0, 255, 0).astype(np.uint8))
    return merged



def _build_region_vector_ignore_mask(
    *,
    text_mask: np.ndarray | None,
    node_mask: np.ndarray | None,
    stroke_mask: np.ndarray | None,
    panel_arrow_mask: np.ndarray | None,
) -> np.ndarray:
    """Build the cleanup mask used for final region vectorization.

    Panel backgrounds are intentionally excluded here. They are already
    protected structurally by dedicated panel nodes, and erasing them at this
    late stage wipes out preserved semantic regions sitting inside each panel.
    """

    return _merge_masks(text_mask, node_mask, stroke_mask, panel_arrow_mask)


def _mask_ignored_regions(image: np.ndarray, ignore_mask: np.ndarray) -> np.ndarray:
    if ignore_mask.size == 0 or not np.any(ignore_mask):
        return image.copy()
    cleaned = image.copy()
    cleaned[ignore_mask > 0] = 255
    return cleaned


def _heal_masked_stage_image(
    image: np.ndarray,
    ignore_mask: np.ndarray,
    kernel_size: int = 7,
) -> np.ndarray:
    cleaned = _mask_ignored_regions(image, ignore_mask)
    if ignore_mask.size == 0 or not np.any(ignore_mask):
        return cleaned

    kernel_size = max(kernel_size | 1, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    healed = cleaned.copy()

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.where(ignore_mask > 0, 255, 0).astype(np.uint8),
        connectivity=8,
    )
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area <= 0:
            continue

        component_mask = np.where(labels == label, 255, 0).astype(np.uint8)
        ring_mask = cv2.dilate(component_mask, kernel, iterations=1)
        ring_mask = cv2.subtract(ring_mask, component_mask)
        ring_pixels = image[ring_mask > 0]
        if ring_pixels.size == 0:
            continue

        quantized = np.clip(((ring_pixels.astype(np.int32) + 8) // 16) * 16, 0, 255)
        colors, counts = np.unique(quantized, axis=0, return_counts=True)
        dominant_quantized = colors[int(np.argmax(counts))]
        dominant_pixels = ring_pixels[np.all(quantized == dominant_quantized, axis=1)]
        dominant = np.median(dominant_pixels, axis=0).astype(np.uint8)
        healed[component_mask > 0] = dominant

    closed = cv2.morphologyEx(healed, cv2.MORPH_CLOSE, kernel)
    expanded_mask = cv2.dilate(ignore_mask, kernel, iterations=1)
    healed[expanded_mask > 0] = closed[expanded_mask > 0]
    return healed


def _mask_for_nodes(
    image: np.ndarray,
    nodes: list[SceneNode],
    padding: int = 0,
    artifacts_dir: Path | None = None,
) -> np.ndarray:
    if not nodes:
        return np.zeros(image.shape[:2], dtype=np.uint8)

    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    for node in nodes:
        if node.shape_hint == 'panel' and node.fill:
            node_mask = _panel_background_mask(image, node)
            if node_mask is None:
                node_mask = _bbox_mask(node.bbox, width, height)
        else:
            node_mask = _rasterize_node_mask(node, width, height, artifacts_dir)
            if node_mask is None:
                node_mask = _bbox_mask(node.bbox, width, height)
        mask = cv2.bitwise_or(mask, node_mask)

    if padding > 0 and np.any(mask):
        kernel_size = max((padding * 2) + 1, 3)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _inpaint_node_and_icon_regions(
    image: np.ndarray,
    scene_graph: SceneGraph,
    node_ids: set[str],
    padding: int,
    artifacts_dir: Path | None = None,
    existing_ignore_mask: np.ndarray | None = None,
    kernel_size: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    mask = _build_inpaint_mask(
        image,
        scene_graph,
        lambda node: node.id in node_ids,
        padding=padding,
        artifacts_dir=artifacts_dir,
    )
    combined_mask = _merge_masks(existing_ignore_mask, mask)
    return _heal_masked_stage_image(image, combined_mask, kernel_size=kernel_size), mask


def _filter_stroke_scene_graph(scene_graph: SceneGraph) -> SceneGraph:
    filtered_nodes = [
        node
        for node in scene_graph.nodes
        if node.type != 'stroke' or _is_exportable_stroke_node(node, scene_graph)
    ]
    if len(filtered_nodes) == len(scene_graph.nodes):
        return scene_graph
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=filtered_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _is_exportable_stroke_node(node: SceneNode, scene_graph: SceneGraph) -> bool:
    x1, y1, x2, y2 = node.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    area = width * height
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    width_ratio = width / max(scene_graph.width, 1)
    height_ratio = height / max(scene_graph.height, 1)
    if area >= canvas_area * 0.25:
        return False
    if width_ratio >= 0.85 and height_ratio >= 0.50:
        return False
    if height_ratio >= 0.85 and width_ratio >= 0.50:
        return False
    return True


def _inpaint_stroke_regions(
    image: np.ndarray,
    scene_graph: SceneGraph,
    padding: int,
    artifacts_dir: Path | None = None,
    existing_ignore_mask: np.ndarray | None = None,
    kernel_size: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    mask = _build_inpaint_mask(
        image,
        scene_graph,
        lambda node: node.type == 'stroke' and _should_inpaint_stroke_node(node, scene_graph),
        padding=padding,
        artifacts_dir=artifacts_dir,
    )
    combined_mask = _merge_masks(existing_ignore_mask, mask)
    return _heal_masked_stage_image(image, combined_mask, kernel_size=kernel_size), mask


def _erase_region_nodes(
    image: np.ndarray,
    nodes: list[SceneNode],
    padding: int = 0,
) -> np.ndarray:
    mask = _mask_for_nodes(image, nodes, padding=padding, artifacts_dir=None)
    return _mask_ignored_regions(image, mask)


def _panel_background_mask(image: np.ndarray, node: SceneNode) -> np.ndarray | None:
    target_bgr = _hex_to_bgr(node.fill)
    if target_bgr is None:
        return None
    height, width = image.shape[:2]
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, width, height)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    color_delta = np.max(np.abs(crop.astype(np.int16) - np.array(target_bgr, dtype=np.int16)), axis=2)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    local_mask = np.where((color_delta <= 32) & (gray >= 170), 255, 0).astype(np.uint8)
    if not np.any(local_mask):
        return None
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = local_mask
    return full_mask




def _should_inpaint_stroke_node(node: SceneNode, scene_graph: SceneGraph) -> bool:
    return _is_exportable_stroke_node(node, scene_graph)


def _build_inpaint_mask(
    image: np.ndarray,
    scene_graph: SceneGraph,
    predicate: Callable[[SceneNode], bool],
    *,
    padding: int,
    artifacts_dir: Path | None,
) -> np.ndarray:
    selected_nodes = [node for node in scene_graph.nodes if predicate(node)]
    return _mask_for_nodes(image, selected_nodes, padding=padding, artifacts_dir=artifacts_dir)


def _rasterize_node_mask(
    node: SceneNode,
    width: int,
    height: int,
    artifacts_dir: Path | None,
) -> np.ndarray | None:
    if artifacts_dir is None or not node.source_mask:
        return None
    mask_path = artifacts_dir / node.source_mask
    if not mask_path.exists():
        return None
    local_mask = read_image(mask_path, cv2.IMREAD_GRAYSCALE)
    if local_mask is None:
        return None
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, width, height)
    target_w = max(x2 - x1, 1)
    target_h = max(y2 - y1, 1)
    if local_mask.shape[1] != target_w or local_mask.shape[0] != target_h:
        local_mask = cv2.resize(local_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = np.where(local_mask > 0, 255, 0).astype(np.uint8)
    return full_mask


def _bbox_mask(bbox: list[int], width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    x1, y1, x2, y2 = _clamp_bbox(bbox, width, height)
    mask[y1:y2, x1:x2] = 255
    return mask



def _prune_region_nodes_by_mask(
    scene_graph: SceneGraph,
    ignore_mask: np.ndarray,
    artifacts_dir: Path | None,
    protected_node_ids: set[str] | None = None,
    coverage_threshold: float = 0.72,
) -> SceneGraph:
    if ignore_mask.size == 0 or not np.any(ignore_mask):
        return scene_graph

    protected_node_ids = protected_node_ids or set()
    width = scene_graph.width
    height = scene_graph.height
    kept_nodes: list[SceneNode] = []
    for node in scene_graph.nodes:
        if not _should_prune_region_node(node, protected_node_ids):
            kept_nodes.append(node)
            continue
        if _should_preserve_large_light_region(node, width, height):
            kept_nodes.append(node)
            continue
        node_mask = _rasterize_node_mask(node, width, height, artifacts_dir)
        if node_mask is None:
            node_mask = _bbox_mask(node.bbox, width, height)
        node_pixels = int(np.count_nonzero(node_mask))
        if node_pixels <= 0:
            kept_nodes.append(node)
            continue
        covered_pixels = int(np.count_nonzero(cv2.bitwise_and(node_mask, ignore_mask)))
        coverage = covered_pixels / max(node_pixels, 1)
        if coverage >= coverage_threshold:
            continue
        kept_nodes.append(node)

    if len(kept_nodes) == len(scene_graph.nodes):
        return scene_graph
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=kept_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )




def _should_preserve_large_light_region(node: SceneNode, width: int, height: int) -> bool:
    if node.type != 'region' or node.shape_hint != 'vector_candidate':
        return False
    if not _looks_like_container_candidate(node, width, height):
        return False
    return _is_light_container_color(node.fill or '', node.stroke or '')


def _should_prune_region_node(node: SceneNode, protected_node_ids: set[str]) -> bool:
    if node.type != 'region' or node.id == 'background-root' or node.id in protected_node_ids:
        return False
    if 'semantic_recovered' in str(node.component_role or '').split():
        return False
    if node.shape_hint in {'panel', 'panel_arrow', 'circle', 'triangle', 'pentagon', 'svg_template'}:
        return False
    return True


def _filter_region_objects(
    scene_graph: SceneGraph,
    region_objects: list[RegionObject],
    text_nodes: list[SceneNode],
) -> list[RegionObject]:
    node_map = {node.id: node for node in scene_graph.nodes}
    filtered: list[RegionObject] = []
    for region_obj in region_objects:
        metadata = dict(region_obj.metadata)
        source_node = node_map.get(region_obj.node_id)
        reject_reason = None
        if source_node is not None:
            if source_node.shape_hint == 'raster_candidate' and _is_template_candidate_bbox(source_node.bbox):
                reject_reason = 'raster-candidate'
            elif _looks_like_large_black_artifact(source_node, scene_graph.width, scene_graph.height):
                reject_reason = 'large-black-fragment'
            elif _matches_text_bbox(source_node.bbox, text_nodes):
                reject_reason = 'text-bbox-like'
        if reject_reason is not None and metadata.get('shape_type') == 'ellipse' and reject_reason != 'large-black-fragment':
            reject_reason = None
        if reject_reason is not None and not _is_lightweight_text_container(source_node, region_obj):
            continue
        filtered.append(
            RegionObject(
                id=region_obj.id,
                node_id=region_obj.node_id,
                outer_path=region_obj.outer_path,
                holes=region_obj.holes[:],
                fill=region_obj.fill,
                fill_opacity=region_obj.fill_opacity,
                stroke=region_obj.stroke,
                metadata=metadata,
            )
        )
    return filtered


def _is_lightweight_text_container(node: SceneNode | None, region_obj: RegionObject | None) -> bool:
    if node is None or node.type != 'region':
        return False
    if 'container_shape' not in str(node.component_role or ''):
        return False
    shape_type = str((region_obj.metadata or {}).get('shape_type') or '') if region_obj is not None else ''
    if shape_type and shape_type != 'rectangle':
        return False
    fill = (region_obj.fill if region_obj is not None else node.fill) or ''
    stroke = (region_obj.stroke if region_obj is not None else node.stroke) or ''
    return _is_light_container_color(fill, stroke)



def _is_light_container_color(fill: str, stroke: str) -> bool:
    if _is_near_black(fill) or _is_near_black(stroke):
        return False
    return _is_light_hex(fill) or _is_light_hex(stroke)



def _is_light_hex(color: str | None) -> bool:
    if color is None:
        return False
    lowered = color.lower()
    if lowered in {'', 'none'}:
        return False
    if not lowered.startswith('#') or len(lowered) != 7:
        return lowered in {'white', '#ffffff'}
    try:
        r = int(lowered[1:3], 16)
        g = int(lowered[3:5], 16)
        b = int(lowered[5:7], 16)
    except ValueError:
        return False
    return min(r, g, b) >= 140 or (r + g + b) >= 560


def _matches_text_bbox(region_bbox: list[int], text_nodes: list[SceneNode]) -> bool:
    region_area = max((region_bbox[2] - region_bbox[0]) * (region_bbox[3] - region_bbox[1]), 1)
    for text_node in text_nodes:
        if _bbox_iou(region_bbox, text_node.bbox) >= 0.8:
            return True
        overlap = _bbox_overlap(region_bbox, text_node.bbox)
        text_area = max((text_node.bbox[2] - text_node.bbox[0]) * (text_node.bbox[3] - text_node.bbox[1]), 1)
        if overlap >= 0.9 and region_area <= text_area * 2.6:
            return True
    return False


def _looks_like_large_black_artifact(node: SceneNode, width: int, height: int) -> bool:
    if not _is_near_black(node.fill) and not _is_near_black(node.stroke):
        return False
    x1, y1, x2, y2 = node.bbox
    area = max(x2 - x1, 1) * max(y2 - y1, 1)
    canvas_area = max(width * height, 1)
    return area >= canvas_area * 0.02


def _is_near_black(color: str | None) -> bool:
    if color is None:
        return False
    lowered = color.lower()
    if lowered in {'#000000', 'black'}:
        return True
    if not lowered.startswith('#') or len(lowered) != 7:
        return False
    try:
        r = int(lowered[1:3], 16)
        g = int(lowered[3:5], 16)
        b = int(lowered[5:7], 16)
    except ValueError:
        return False
    return max(r, g, b) <= 24


def _expand_bbox(bbox: list[int], width: int, height: int, margin: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    return _clamp_bbox([x1 - margin, y1 - margin, x2 + margin, y2 + margin], width, height)


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _choose_processing_sources(
    cfg: PipelineConfig,
    analysis,
    enhanced_path: Path,
    enhancement_scale: float,
) -> tuple[Path, Path, float]:
    if analysis.route_type == 'wide_hires':
        return cfg.input_path, cfg.input_path, 1.0
    return cfg.input_path, enhanced_path, enhancement_scale


def _load_color_image(path: Path | np.ndarray) -> np.ndarray:
    if isinstance(path, np.ndarray):
        if path.ndim == 2:
            return cv2.cvtColor(path, cv2.COLOR_GRAY2BGR)
        return path
    image = read_image(path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Failed to load image: {path}')
    return image
