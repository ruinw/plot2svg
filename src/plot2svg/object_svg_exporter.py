"""SVG export orchestration for object-driven scene graph primitives."""

from __future__ import annotations

from .renderers.common import bbox_contains_point as _bbox_contains_point
from .renderers.common import bbox_overlap as _bbox_overlap
from .renderers.common import expand_bbox as _expand_bbox
from .renderers.common import union_bbox as _union_bbox
from .renderers.edge_renderer import render_graph_edge as _render_graph_edge
from .renderers.object_renderer import _should_prune_raster_object
from .renderers.object_renderer import render_icon_object as _render_icon_object
from .renderers.object_renderer import render_node_object as _render_node_object
from .renderers.object_renderer import render_raster_object as _render_raster_object
from .renderers.object_renderer import render_raster_template_override as _render_raster_template_override
from .renderers.region_renderer import region_sort_key as _region_sort_key
from .renderers.region_renderer import render_region_object as _render_region_object
from .renderers.text_renderer import is_lightweight_text_container as _is_lightweight_text_container
from .renderers.text_renderer import render_text_node as _render_text_node
from .renderers.text_renderer import text_nodes as _text_nodes
from .renderers.text_renderer import text_overlap_score as _text_overlap_score
from .renderers.text_renderer import text_overlaps_template_exclusion as _text_overlaps_template_exclusion
from .scene_graph import RegionObject, SceneGraph, SceneNode, SceneObject
from .svg_templates import render_svg_template


def export_object_scene_graph(
    scene_graph: SceneGraph,
    fallback_region_map: dict[str, object] | None = None,
    fallback_stroke_map: dict[str, object] | None = None,
) -> list[str]:
    """Render object-driven SVG fragments with text forced to the top layer."""

    fallback_region_map = fallback_region_map or {}
    fallback_stroke_map = fallback_stroke_map or {}
    node_map = {node.id: node for node in scene_graph.nodes}
    absorbed_region_ids = _absorbed_region_ids(scene_graph)
    covered_region_ids = {
        obj.node_id
        for obj in scene_graph.region_objects
        if obj.node_id not in absorbed_region_ids
    }
    covered_region_ids.update(
        obj.node_id
        for obj in scene_graph.raster_objects
        if obj.node_id not in absorbed_region_ids
    )
    covered_stroke_ids = {edge.backbone_id for edge in scene_graph.graph_edges if edge.backbone_id}
    covered_node_ids = {
        obj.node_id
        for obj in scene_graph.node_objects
        if obj.node_id not in absorbed_region_ids
    }
    fragments: list[str] = []

    template_groups = _template_candidate_groups(scene_graph, node_map)
    template_group_bboxes = _template_group_bboxes(scene_graph, node_map, template_groups)
    region_objects = [
        region_obj
        for region_obj in scene_graph.region_objects
        if region_obj.node_id not in absorbed_region_ids
    ]
    region_objects.sort(key=lambda item: _region_sort_key(item, node_map), reverse=True)
    emitted_template_groups: set[str] = set()
    template_text_exclusion_bboxes: list[list[int]] = []
    fragments.extend(_render_network_container_backdrops(scene_graph, node_map, absorbed_region_ids))
    for region_obj in region_objects:
        if _should_skip_region_object_for_template_group(region_obj, node_map, template_groups):
            continue
        if _should_skip_region_object_inside_template_bbox(region_obj, node_map, template_group_bboxes):
            continue
        if _should_drop_graphic_near_text(node_map.get(region_obj.node_id), scene_graph, region_obj=region_obj):
            continue
        detail_template = _render_detail_group_template_override(region_obj, scene_graph, node_map)
        if detail_template is not None:
            group_key, fragment, template_bbox = detail_template
            if group_key in emitted_template_groups:
                continue
            emitted_template_groups.add(group_key)
            if fragment is not None:
                template_text_exclusion_bboxes.append(template_bbox[:])
                fragments.append(fragment)
            continue
        fragment = _render_region_object(region_obj, scene_graph, node_map)
        if fragment is not None:
            template_bbox = _template_bbox_for_region_object(region_obj, node_map)
            if template_bbox is not None:
                template_text_exclusion_bboxes.append(template_bbox)
            fragments.append(fragment)

    for node in sorted(scene_graph.nodes, key=lambda item: item.z_index):
        if node.id in absorbed_region_ids:
            continue
        if node.group_id and (f'detail-template:{node.group_id}' in emitted_template_groups or node.group_id in template_groups):
            continue
        if node.type == 'region' and node.id not in covered_region_ids and node.id in fallback_region_map:
            if _should_drop_graphic_near_text(node, scene_graph):
                continue
            fallback_fragment = fallback_region_map[node.id].svg_fragment
            if _should_emit_region_fallback(node, fallback_fragment):
                fragments.append(fallback_fragment)

    for icon_obj in scene_graph.icon_objects:
        if icon_obj.node_id in absorbed_region_ids:
            continue
        fragments.append(_render_icon_object(icon_obj))

    for raster_obj in scene_graph.raster_objects:
        if raster_obj.node_id in absorbed_region_ids:
            continue
        if _should_prune_raster_object(raster_obj):
            continue
        template_fragment = _render_raster_template_override(raster_obj, scene_graph, node_map)
        if template_fragment is not None:
            template_text_exclusion_bboxes.append(raster_obj.bbox[:])
            fragments.append(template_fragment)
            continue
        fragments.append(_render_raster_object(raster_obj))

    for node_obj in scene_graph.node_objects:
        if node_obj.node_id in absorbed_region_ids:
            continue
        fragments.append(_render_node_object(node_obj))

    for edge in scene_graph.graph_edges:
        fragments.extend(_render_graph_edge(edge, scene_graph, node_map))

    for node in sorted(scene_graph.nodes, key=lambda item: item.z_index):
        if node.id in absorbed_region_ids:
            continue
        if node.type == 'stroke' and node.id not in covered_stroke_ids and node.id in fallback_stroke_map:
            if _should_drop_graphic_near_text(node, scene_graph):
                continue
            fragments.append(
                f"<path id='{node.id}' d='{fallback_stroke_map[node.id].svg_fragment}' "
                f"fill='none' stroke='#000000' />"
            )

    for text_node in sorted(_text_nodes(scene_graph), key=lambda item: item.z_index):
        if _text_overlaps_template_exclusion(text_node, template_text_exclusion_bboxes):
            continue
        text_fragment = _render_text_node(text_node)
        if text_fragment is not None:
            fragments.append(text_fragment)

    return fragments


def _render_network_container_backdrops(
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
    absorbed_region_ids: set[str],
) -> list[str]:
    fragments: list[str] = []
    for obj in scene_graph.objects:
        if obj.object_type != 'network_container':
            continue
        if any(node_id in absorbed_region_ids for node_id in obj.node_ids):
            continue
        fragments.append(_render_network_container_backdrop(obj, node_map))
    return fragments


def _render_network_container_backdrop(obj: SceneObject, node_map: dict[str, SceneNode]) -> str:
    x1, y1, x2, y2 = obj.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    cx = x1 + width / 2.0
    cy = y1 + height / 2.0
    rx = max(width / 2.0, 1.0)
    ry = max(height / 2.0, 1.0)
    fill = _network_container_fill(obj, node_map)
    return (
        f"<ellipse id='{obj.id}-backdrop' class='region network-container-backdrop' "
        f"data-object-id='{obj.id}' data-object-type='network_container' "
        f"cx='{cx:.1f}' cy='{cy:.1f}' rx='{rx:.1f}' ry='{ry:.1f}' "
        f"fill='{fill}' stroke='{fill}' fill-opacity='0.220' stroke-opacity='0.350' />"
    )


def _network_container_fill(obj: SceneObject, node_map: dict[str, SceneNode]) -> str:
    for node_id in obj.node_ids:
        node = node_map.get(node_id)
        if node is not None and node.type == 'region' and node.fill and node.fill not in {'none', '#ffffff'}:
            return node.fill
    return '#d9e6f2'


def _absorbed_region_ids(scene_graph: SceneGraph) -> set[str]:
    ids: set[str] = set()
    for primitive in scene_graph.stroke_primitives:
        ids.update(str(region_id) for region_id in primitive.metadata.get('absorbed_region_ids', []))
    for edge in scene_graph.graph_edges:
        ids.update(str(region_id) for region_id in edge.metadata.get('absorbed_region_ids', []))
    return ids


def _template_candidate_groups(
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> set[str]:
    groups: set[str] = set()
    for region_obj in scene_graph.region_objects:
        node = node_map.get(region_obj.node_id)
        if node is None or not str(node.id).startswith('container-detail-region-'):
            continue
        group_id = str(node.group_id or '')
        if not group_id:
            continue
        if _render_detail_group_template_override(region_obj, scene_graph, node_map) is not None:
            groups.add(group_id)
    return groups


def _should_skip_region_object_for_template_group(
    region_obj: RegionObject,
    node_map: dict[str, SceneNode],
    template_groups: set[str],
) -> bool:
    node = node_map.get(region_obj.node_id)
    if node is None:
        return False
    group_id = str(node.group_id or '')
    if not group_id or group_id not in template_groups:
        return False
    if str(node.id).startswith('container-detail-region-'):
        return False
    role = str(node.component_role or '')
    return 'container_shape' in role or 'container_boundary' in role


def _template_group_bboxes(
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
    template_groups: set[str],
) -> dict[str, list[int]]:
    boxes: dict[str, list[int]] = {}
    for group_id in template_groups:
        group_nodes = [
            node for node in scene_graph.nodes
            if node.type == 'region'
            and node.group_id == group_id
            and str(node.id).startswith('container-detail-region-')
        ]
        if not group_nodes:
            continue
        boxes[group_id] = _union_bbox(node.bbox for node in group_nodes)
    return boxes


def _should_skip_region_object_inside_template_bbox(
    region_obj: RegionObject,
    node_map: dict[str, SceneNode],
    template_group_bboxes: dict[str, list[int]],
) -> bool:
    node = node_map.get(region_obj.node_id)
    if node is None:
        return False
    if str(node.id).startswith('container-detail-region-'):
        return False
    if str(node.component_role or '').find('container_shape') >= 0 or str(node.component_role or '').find('container_boundary') >= 0:
        return False
    node_bbox = node.bbox
    node_area = max((node_bbox[2] - node_bbox[0]) * (node_bbox[3] - node_bbox[1]), 1)
    center_x = (node_bbox[0] + node_bbox[2]) / 2.0
    center_y = (node_bbox[1] + node_bbox[3]) / 2.0
    for template_bbox in template_group_bboxes.values():
        overlap = _bbox_overlap(node_bbox, template_bbox)
        template_area = max((template_bbox[2] - template_bbox[0]) * (template_bbox[3] - template_bbox[1]), 1)
        template_width = max(template_bbox[2] - template_bbox[0], 1)
        template_height = max(template_bbox[3] - template_bbox[1], 1)
        if overlap >= 0.95 and node_area <= template_area * 0.22:
            return True
        if _bbox_contains_point(template_bbox, center_x, center_y) and node_area <= template_area * 0.03:
            return True
        expanded_bbox = _expand_bbox(
            template_bbox,
            margin_x=min(max(int(template_width * 0.35), 24), 80),
            margin_y=min(max(int(template_height * 0.10), 12), 36),
        )
        if _bbox_contains_point(expanded_bbox, center_x, center_y) and node_area <= template_area * 0.01:
            return True
    return False


def _should_emit_region_fallback(node: SceneNode, fragment: str) -> bool:
    if not fragment or " d=''" in fragment or ' d=""' in fragment:
        return False
    if _fragment_has_pure_black_fill(fragment):
        return False
    if node.shape_hint == 'svg_template':
        return False
    if node.component_role != 'container_shape':
        return True
    if not node.group_id:
        return True
    return not str(node.group_id).startswith('component-text-overlay-')


def _render_detail_group_template_override(
    region_obj: RegionObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> tuple[str, str | None, list[int]] | None:
    node = node_map.get(region_obj.node_id)
    if node is None:
        return None
    if not str(node.id).startswith('container-detail-region-'):
        return None
    group_id = str(node.group_id or '')
    if not group_id:
        return None

    group_nodes = [
        candidate
        for candidate in scene_graph.nodes
        if candidate.type == 'region'
        and candidate.group_id == group_id
        and str(candidate.id).startswith('container-detail-region-')
    ]
    if len(group_nodes) < 2:
        return None

    bbox = _union_bbox(node.bbox for node in group_nodes)
    width = max(bbox[2] - bbox[0], 1)
    height = max(bbox[3] - bbox[1], 1)
    if width < 24 or height < 24:
        return None

    template_name = _infer_detail_group_template_name(scene_graph, bbox, group_id)
    if template_name is None:
        return None

    container_fill = next(
        (
            candidate.fill
            for candidate in scene_graph.nodes
            if candidate.type == 'region'
            and candidate.group_id == group_id
            and str(candidate.component_role or '').find('container_shape') >= 0
            and candidate.fill
        ),
        None,
    )
    fill = container_fill or region_obj.fill or node.fill or '#d9e6f2'
    fragment = render_svg_template(
        template_name,
        bbox,
        element_id=f'detail-template-{group_id}',
        node_id=f'detail-template-{group_id}',
        fill=fill,
        stroke=node.stroke,
    )
    return f'detail-template:{group_id}', fragment, bbox


def _infer_detail_group_template_name(scene_graph: SceneGraph, bbox: list[int], group_id: str) -> str | None:
    context = _detail_group_text_context(scene_graph, bbox, group_id)
    lowered = context.lower()
    if 'feature engineering' in lowered or 'maf parsing' in lowered:
        return 'feature_panel'
    if 'node id' in lowered or ('normalization' in lowered and 'step' in lowered):
        return 'stack_panel'
    if any(keyword in lowered for keyword in ('time (years)', 'high risk', 'low risk')):
        return 'survival_curve'
    gene_like = sum(keyword in lowered for keyword in ('gene', 'disease', 'pathway', 'heterogeneous', 'node embedding', 'graph construction'))
    if 'node embedding' in lowered and gene_like >= 3:
        return 'hetero_graph'
    if any(keyword in lowered for keyword in ('attention weight', 'attention score', 'gene heatmap', 'heatmap')):
        return 'heatmap'
    return None


def _detail_group_text_context(scene_graph: SceneGraph, bbox: list[int], group_id: str) -> str:
    anchor_id = group_id.replace('component-', '', 1)
    anchor_text = ''
    for node in scene_graph.nodes:
        if node.id == anchor_id and node.type == 'text' and (node.text_content or '').strip():
            anchor_text = str(node.text_content)
            break

    x1, y1, x2, y2 = bbox
    margin = 48
    nearby: list[str] = []
    for node in scene_graph.nodes:
        if node.type != 'text' or not (node.text_content or '').strip():
            continue
        bx1, by1, bx2, by2 = node.bbox
        if bx2 < x1 - margin or bx1 > x2 + margin or by2 < y1 - margin or by1 > y2 + margin:
            continue
        nearby.append(str(node.text_content))
    if anchor_text:
        nearby.insert(0, anchor_text)
    return ' '.join(nearby)


def _fragment_has_pure_black_fill(fragment: str) -> bool:
    lowered = fragment.lower()
    return (
        "fill='#000000'" in lowered
        or 'fill="#000000"' in lowered
        or "fill='black'" in lowered
        or 'fill="black"' in lowered
    )


def _should_drop_pure_black_region_fragment(fragment: str) -> bool:
    lowered = fragment.lower()
    if not _fragment_has_pure_black_fill(lowered):
        return False
    if any(token in lowered for token in ["class='edge'", 'class="edge"', "class='edge-arrow'", 'class="edge-arrow"', "class='node'", 'class="node"', '<text', "data-node-type='stroke'", 'data-node-type="stroke"']):
        return False
    return any(
        token in lowered
        for token in [
            "class='region'",
            'class="region"',
            "data-node-type='region'",
            'data-node-type="region"',
            "id='region-",
            'id="region-',
            "id='panel-region-",
            'id="panel-region-',
        ]
    )


def _should_drop_graphic_near_text(node: SceneNode | None, scene_graph: SceneGraph, region_obj: RegionObject | None = None) -> bool:
    if node is None or node.type not in {'region', 'stroke'}:
        return False
    if node.type == 'region' and node.shape_hint in {'panel', 'panel_arrow', 'svg_template'}:
        return False
    if _is_lightweight_text_container(node, region_obj):
        return False
    candidate_bbox = node.bbox
    for text_node in _text_nodes(scene_graph):
        if _text_overlap_score(candidate_bbox, text_node.bbox) > 0.6:
            return True
    return False


def _template_bbox_for_region_object(
    region_obj: RegionObject,
    node_map: dict[str, SceneNode],
) -> list[int] | None:
    if region_obj.metadata.get('shape_type') == 'svg_template':
        template_bbox = region_obj.metadata.get('template_bbox')
        if template_bbox:
            return [int(value) for value in template_bbox]
    node = node_map.get(region_obj.node_id)
    if node is not None and node.shape_hint == 'svg_template':
        return node.bbox[:]
    return None
