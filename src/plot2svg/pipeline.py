"""Top-level pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

import cv2
import numpy as np

from .bbox_utils import (
    _bbox_gap,
    _bbox_iou,
    _bbox_overlap,
    _clamp_bbox,
    _contains_bbox,
    _expand_bbox,
    _matches_text_bbox,
    _overlaps_existing_region,
)
from .color_utils import (
    _bgr_to_hex,
    _hex_to_bgr,
    _is_light_container_color,
    _is_light_hex,
    _is_near_black,
    _is_near_white,
    _sample_arrow_fill_color,
    _sample_panel_border_color,
    _sample_panel_fill,
)
from .image_io import read_image, write_image
from .inpaint import (
    _bbox_mask,
    _erase_region_nodes,
    _heal_masked_stage_image,
    _inpaint_node_and_icon_regions,
    _inpaint_stroke_regions,
    _is_exportable_stroke_node,
    _mask_for_nodes,
    _rasterize_node_mask,
    _should_inpaint_stroke_node,
)
from .panel_detection import (
    _attach_panel_background_regions,
    _cluster_text_columns,
    _collect_boundary_arrow_boxes,
    _detect_panel_arrow_regions,
    _detect_panel_background_nodes,
    _estimate_visible_panel_bbox,
    _inject_panel_background_regions,
    _merge_nearby_bboxes,
    _select_boundary_arrow_boxes,
    _synthesize_right_arrow_path,
)
from .semantic_labeling import (
    _detect_raster_objects,
    _extract_icon_objects,
    _filter_node_objects,
    _filter_region_objects,
    _is_lightweight_text_container,
    _looks_like_data_chart,
    _looks_like_large_black_artifact,
    _promote_svg_template_nodes,
    _resolve_semantic_raster_objects,
    _should_route_template_candidate_to_icon_object,
)

from .analyze import analyze_image
from .config import PipelineConfig
from .enhance import enhance_image
from .export_svg import export_svg
from .graph_builder import build_graph
from .node_detector import detect_nodes
from .layout_refiner import refine_layout
from .ocr import extract_text_overlays, inpaint_text_nodes
from .detect_structure import detect_structures
from .region_vectorizer import vectorize_region_objects
from .scene_graph import IconObject, RasterObject, RegionObject, SceneGraph, SceneNode, SceneObject, build_object_instances, build_scene_graph, enrich_region_styles, promote_component_groups
from .segment import ComponentProposal, propose_components
from .stroke_detector import detect_strokes
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


def _configure_cv_runtime_stability() -> None:
    """Clamp OpenCV runtime settings to a stable baseline for repeated runs."""
    cv2.setNumThreads(1)
    if hasattr(cv2, "ocl"):
        cv2.ocl.setUseOpenCL(False)


def run_pipeline(cfg: PipelineConfig) -> PipelineArtifacts:
    """Run the subtraction-style pipeline and persist protocol artifacts."""

    _configure_cv_runtime_stability()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_image(cfg.input_path, cfg=cfg)
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
        cfg=cfg,
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
    scene_graph = detect_structures(scene_graph, cfg)
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
    scene_graph = build_graph(scene_graph, cfg)
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
