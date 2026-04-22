"""Component manifest generation for debug and editor mapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scene_graph import GraphEdge, IconObject, NodeObject, RasterObject, RegionObject, SceneGraph, SceneGroup, SceneNode

_DISPLAY_PREFIX_BY_NODE_TYPE = {
    'text': 'TXT',
    'region': 'REG',
    'stroke': 'STK',
}
_BASIC_SHAPES = {'rectangle', 'circle', 'ellipse', 'panel_arrow_template'}


def build_component_manifest(scene_graph: SceneGraph, segmentation_backend: str = 'opencv') -> dict[str, Any]:
    """Build a stable manifest that maps scene graph items to SVG elements."""

    counters: dict[str, int] = {}
    components: list[dict[str, Any]] = []
    node_map = {node.id: node for node in scene_graph.nodes}

    for node in sorted(scene_graph.nodes, key=lambda item: (item.z_index, item.id)):
        if node.id == 'background-root' or node.type == 'background':
            continue
        display_id = _next_display_id(counters, _node_prefix(node))
        components.append(_node_entry(node, display_id, segmentation_backend))

    for group in sorted(scene_graph.groups, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'GRP')
        components.append(_group_entry(group, display_id, segmentation_backend))

    for region_obj in sorted(scene_graph.region_objects, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'ROB')
        components.append(_region_object_entry(region_obj, display_id, node_map, segmentation_backend))

    for icon_obj in sorted(scene_graph.icon_objects, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'ICO')
        components.append(_icon_object_entry(icon_obj, display_id, segmentation_backend))

    for raster_obj in sorted(scene_graph.raster_objects, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'RAS')
        components.append(_raster_object_entry(raster_obj, display_id, segmentation_backend))

    for node_obj in sorted(scene_graph.node_objects, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'NOD')
        components.append(_node_object_entry(node_obj, display_id, segmentation_backend))

    for edge in sorted(scene_graph.graph_edges, key=lambda item: item.id):
        display_id = _next_display_id(counters, 'EDG')
        components.append(_edge_entry(edge, display_id, segmentation_backend))

    return {
        'version': 1,
        'canvas': {'width': scene_graph.width, 'height': scene_graph.height},
        'components': components,
        'summary': {'component_count': len(components)},
    }


def write_component_manifest(scene_graph: SceneGraph, path: Path, segmentation_backend: str = 'opencv') -> None:
    """Write the component manifest JSON beside pipeline artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_component_manifest(scene_graph, segmentation_backend), indent=2), encoding='utf-8')


def _next_display_id(counters: dict[str, int], prefix: str) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    return f'{prefix}{counters[prefix]:03d}'


def _node_prefix(node: SceneNode) -> str:
    return _DISPLAY_PREFIX_BY_NODE_TYPE.get(node.type, 'NOD')


def _base_entry(
    *,
    display_id: str,
    source_kind: str,
    source_id: str,
    component_type: str,
    bbox: list[int] | None,
    svg_id: str,
    source_stage: str,
    editable_strategy: str,
    segmentation_backend: str,
) -> dict[str, Any]:
    return {
        'display_id': display_id,
        'source_kind': source_kind,
        'source_id': source_id,
        'component_type': component_type,
        'bbox': bbox or [],
        'svg_id': svg_id,
        'source_stage': source_stage,
        'segmentation_backend': segmentation_backend,
        'editable_strategy': editable_strategy,
        'template_id': f'tpl-{display_id}',
        'final_svg_id': svg_id,
    }


def _node_entry(node: SceneNode, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    entry = _base_entry(
        display_id=display_id,
        source_kind='node',
        source_id=node.id,
        component_type=node.type,
        bbox=node.bbox[:],
        svg_id=node.id,
        source_stage=_source_stage(node.id, node.type),
        editable_strategy=_node_editable_strategy(node),
        segmentation_backend=segmentation_backend,
    )
    entry.update({
        'z_index': node.z_index,
        'confidence': node.confidence,
        'vector_mode': node.vector_mode,
    })
    _add_optional(entry, 'group_id', node.group_id)
    _add_optional(entry, 'component_role', node.component_role)
    _add_optional(entry, 'source_mask', node.source_mask)
    _add_optional(entry, 'shape_hint', node.shape_hint)
    _add_optional(entry, 'text_content', node.text_content)
    return entry


def _group_entry(group: SceneGroup, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    entry = _base_entry(
        display_id=display_id,
        source_kind='group',
        source_id=group.id,
        component_type=group.role,
        bbox=group.bbox[:],
        svg_id=group.id,
        source_stage='grouping',
        editable_strategy='group',
        segmentation_backend=segmentation_backend,
    )
    entry['child_ids'] = group.child_ids[:]
    _add_optional(entry, 'shape_type', group.shape_type)
    _add_optional(entry, 'direction', group.direction)
    if group.contains_group_ids:
        entry['contains_group_ids'] = group.contains_group_ids[:]
    return entry


def _region_object_entry(
    region_obj: RegionObject,
    display_id: str,
    node_map: dict[str, SceneNode],
    segmentation_backend: str,
) -> dict[str, Any]:
    shape_type = _metadata_shape_type(region_obj.metadata)
    return _object_entry(
        display_id=display_id,
        source_kind='region_object',
        source_id=region_obj.id,
        component_type='region',
        node_id=region_obj.node_id,
        bbox=_metadata_bbox(region_obj.metadata) or _node_bbox(node_map, region_obj.node_id),
        metadata=region_obj.metadata,
        segmentation_backend=segmentation_backend,
        editable_strategy='native_shape' if shape_type in _BASIC_SHAPES else 'native_path',
    )


def _icon_object_entry(icon_obj: IconObject, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    return _object_entry(
        display_id=display_id,
        source_kind='icon_object',
        source_id=icon_obj.id,
        component_type='icon',
        node_id=icon_obj.node_id,
        bbox=icon_obj.bbox,
        metadata=icon_obj.metadata,
        segmentation_backend=segmentation_backend,
        editable_strategy='native_icon',
    )


def _raster_object_entry(raster_obj: RasterObject, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    entry = _object_entry(
        display_id=display_id,
        source_kind='raster_object',
        source_id=raster_obj.id,
        component_type='raster',
        node_id=raster_obj.node_id,
        bbox=raster_obj.bbox,
        metadata=raster_obj.metadata,
        segmentation_backend=segmentation_backend,
        editable_strategy='raster_fallback',
    )
    entry['fallback_reason'] = str(
        raster_obj.metadata.get('fallback_reason')
        or raster_obj.metadata.get('shape_hint')
        or 'complex_raster_component'
    )
    return entry


def _node_object_entry(node_obj: NodeObject, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    radius = int(round(node_obj.radius))
    cx, cy = node_obj.center
    bbox = [int(round(cx - radius)), int(round(cy - radius)), int(round(cx + radius)), int(round(cy + radius))]
    return _object_entry(
        display_id=display_id,
        source_kind='node_object',
        source_id=node_obj.id,
        component_type=str(node_obj.metadata.get('shape_type', 'node')),
        node_id=node_obj.node_id,
        bbox=bbox,
        metadata=node_obj.metadata,
        segmentation_backend=segmentation_backend,
        editable_strategy='native_shape',
    )


def _edge_entry(edge: GraphEdge, display_id: str, segmentation_backend: str) -> dict[str, Any]:
    entry = _object_entry(
        display_id=display_id,
        source_kind='graph_edge',
        source_id=edge.id,
        component_type='edge',
        node_id=edge.backbone_id,
        bbox=_path_bbox(edge.path),
        metadata=edge.metadata,
        segmentation_backend=segmentation_backend,
        editable_strategy='native_path',
    )
    _add_optional(entry, 'source_node_id', edge.source_id)
    _add_optional(entry, 'target_node_id', edge.target_id)
    return entry


def _object_entry(
    *,
    display_id: str,
    source_kind: str,
    source_id: str,
    component_type: str,
    node_id: str | None,
    bbox: list[int] | None,
    metadata: dict[str, object],
    segmentation_backend: str,
    editable_strategy: str,
) -> dict[str, Any]:
    entry = _base_entry(
        display_id=display_id,
        source_kind=source_kind,
        source_id=source_id,
        component_type=component_type,
        bbox=bbox,
        svg_id=source_id,
        source_stage=str(metadata.get('source', 'semantic')),
        editable_strategy=editable_strategy,
        segmentation_backend=segmentation_backend,
    )
    _add_optional(entry, 'node_id', node_id)
    shape_type = _metadata_shape_type(metadata)
    _add_optional(entry, 'shape_type', shape_type)
    return entry


def _node_editable_strategy(node: SceneNode) -> str:
    if node.type == 'text':
        return 'native_text'
    if node.type == 'stroke':
        return 'native_path'
    if node.type == 'region' and node.shape_hint in {'circle', 'ellipse', 'rectangle', 'panel', 'panel_arrow'}:
        return 'native_shape'
    return 'native_path'


def _metadata_shape_type(metadata: dict[str, object]) -> str | None:
    shape_type = metadata.get('shape_type') or metadata.get('shape_hint')
    if shape_type is None:
        return None
    return str(shape_type)


def _node_bbox(node_map: dict[str, SceneNode], node_id: str) -> list[int] | None:
    node = node_map.get(node_id)
    if node is None:
        return None
    return node.bbox[:]


def _metadata_bbox(metadata: dict[str, object]) -> list[int] | None:
    bbox = metadata.get('template_bbox')
    if isinstance(bbox, list) and len(bbox) == 4:
        return [int(value) for value in bbox]
    return None


def _path_bbox(path: list[list[float]]) -> list[int]:
    if not path:
        return []
    xs = [point[0] for point in path]
    ys = [point[1] for point in path]
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]


def _source_stage(source_id: str, component_type: str) -> str:
    for stage in ('stage1', 'stage2', 'stage3'):
        if source_id.startswith(f'{stage}-'):
            return stage
    if source_id.startswith('text-') or source_id.startswith('text_overlay') or component_type == 'text':
        return 'ocr'
    if source_id.startswith(('panel-', 'container-detail-', 'fan-synthetic')):
        return 'synthetic'
    return 'scene_graph'


def _add_optional(entry: dict[str, Any], key: str, value: object | None) -> None:
    if value is not None:
        entry[key] = value