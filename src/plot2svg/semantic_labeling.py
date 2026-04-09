"""Semantic labeling helpers extracted from the pipeline orchestration module."""

from __future__ import annotations

import re

import numpy as np

from .bbox_utils import _bbox_gap, _bbox_iou, _clamp_bbox, _contains_bbox, _matches_text_bbox
from .color_utils import _is_light_container_color, _is_near_black
from .icon_processor import IconProcessor
from .icon_vectorizer import vectorize_clean_image
from .scene_graph import IconObject, RasterObject, RegionObject, SceneGraph, SceneNode
from .svg_templates import append_template_role, infer_template_from_text_context, match_svg_template


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



def _looks_like_data_chart(text_content: str) -> bool:
    lowered = text_content.lower()
    return any(keyword in lowered for keyword in _CHART_TEXT_KEYWORDS)



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



def _looks_like_large_black_artifact(node: SceneNode, width: int, height: int) -> bool:
    if not _is_near_black(node.fill) and not _is_near_black(node.stroke):
        return False
    x1, y1, x2, y2 = node.bbox
    area = max(x2 - x1, 1) * max(y2 - y1, 1)
    canvas_area = max(width * height, 1)
    return area >= canvas_area * 0.02
