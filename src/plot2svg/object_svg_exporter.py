"""SVG export from object-driven scene graph primitives."""

from __future__ import annotations

from html import escape
import math
import re

from .color_utils import _is_dark_color, _is_light_container_color, _is_light_hex, _is_pure_black_region_fill
from .scene_graph import GraphEdge, IconObject, NodeObject, RasterObject, RegionObject, SceneGraph, SceneNode
from .svg_templates import SVG_TEMPLATES, extract_template_name, infer_template_from_text_context, render_svg_template


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


def _bbox_contains_point(bbox: list[int], x: float, y: float) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _expand_bbox(bbox: list[int], margin_x: int, margin_y: int) -> list[int]:
    return [bbox[0] - margin_x, bbox[1] - margin_y, bbox[2] + margin_x, bbox[3] + margin_y]


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

def _region_sort_key(region_obj: RegionObject, node_map: dict[str, SceneNode]) -> float:
    node = node_map.get(region_obj.node_id)
    if node is not None:
        x1, y1, x2, y2 = node.bbox
        return float(max(x2 - x1, 1) * max(y2 - y1, 1))
    ellipse = region_obj.metadata.get('ellipse') or {}
    if ellipse:
        return math.pi * float(ellipse.get('rx', 0.0)) * float(ellipse.get('ry', 0.0))
    return 0.0


def _render_region_object(
    region_obj: RegionObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> str | None:
    if region_obj.metadata.get('entity_valid') is False:
        return None
    if region_obj.metadata.get('shape_type') == 'svg_template':
        template_name = str(region_obj.metadata.get('template_name') or '')
        template_bbox = region_obj.metadata.get('template_bbox') or [0, 0, 1, 1]
        fragment = render_svg_template(
            template_name,
            [int(value) for value in template_bbox],
            element_id=region_obj.id,
            node_id=region_obj.node_id,
            fill=region_obj.fill,
            stroke=region_obj.stroke,
        )
        return fragment
    if _should_skip_background_rectangle(region_obj):
        return None
    if _is_pure_black_region_fill(region_obj.fill):
        return None
    if _is_large_dark_region(region_obj, scene_graph, node_map):
        return None

    fill = region_obj.fill or 'none'
    stroke = region_obj.stroke or '#000000'
    fill_opacity = (
        f" fill-opacity='{region_obj.fill_opacity:.3f}'"
        if region_obj.fill_opacity is not None and region_obj.fill_opacity < 0.999
        else ''
    )
    circle_hint_fragment = _render_circle_hint_region_object(region_obj, node_map, fill, stroke, fill_opacity)
    if circle_hint_fragment is not None:
        return circle_hint_fragment
    if region_obj.metadata.get('shape_type') == 'circle':
        circle = region_obj.metadata.get('circle') or {}
        cx = float(circle.get('cx', 0.0))
        cy = float(circle.get('cy', 0.0))
        radius = float(circle.get('r', 0.0))
        return (
            f"<circle id='{region_obj.id}' class='region' data-node-id='{region_obj.node_id}' data-shape-type='circle' "
            f"cx='{cx:.1f}' cy='{cy:.1f}' r='{radius:.1f}' fill='{fill}' stroke='{stroke}'{fill_opacity} />"
        )
    if region_obj.metadata.get('shape_type') == 'ellipse':
        ellipse = region_obj.metadata.get('ellipse') or {}
        cx = float(ellipse.get('cx', 0.0))
        cy = float(ellipse.get('cy', 0.0))
        rx = float(ellipse.get('rx', 0.0))
        ry = float(ellipse.get('ry', 0.0))
        rotation = float(ellipse.get('rotation', 0.0))
        transform = '' if abs(rotation) < 0.5 else f" transform='rotate({rotation:.1f} {cx:.1f} {cy:.1f})'"
        return (
            f"<ellipse id='{region_obj.id}' class='region' data-node-id='{region_obj.node_id}' data-shape-type='ellipse' "
            f"cx='{cx:.1f}' cy='{cy:.1f}' rx='{rx:.1f}' ry='{ry:.1f}'{transform} fill='{fill}' stroke='{stroke}'{fill_opacity} />"
        )
    if region_obj.metadata.get('shape_type') == 'rectangle':
        rectangle = region_obj.metadata.get('rectangle') or {}
        x = float(rectangle.get('x', 0.0))
        y = float(rectangle.get('y', 0.0))
        width = float(rectangle.get('width', 0.0))
        height = float(rectangle.get('height', 0.0))
        node = node_map.get(region_obj.node_id)
        rounded = ''
        if node is not None and node.shape_hint == 'panel':
            radius = max(8.0, min(min(width, height) * 0.18, 18.0))
            rounded = f" rx='{radius:.1f}' ry='{radius:.1f}'"
        return (
            f"<rect id='{region_obj.id}' class='region' data-node-id='{region_obj.node_id}' data-shape-type='rectangle' "
            f"x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{height:.1f}'{rounded} fill='{fill}' stroke='{stroke}'{fill_opacity} />"
        )
    if region_obj.metadata.get('shape_type') == 'panel_arrow_template':
        template_bbox = region_obj.metadata.get('template_bbox') or node_map.get(region_obj.node_id).bbox if node_map.get(region_obj.node_id) is not None else [0, 0, 1, 1]
        return _render_panel_arrow_template(region_obj, [int(value) for value in template_bbox], fill, stroke, fill_opacity)
    commands = [region_obj.outer_path, *region_obj.holes]
    fill_rule = " fill-rule='evenodd'" if region_obj.holes else ''
    return (
        f"<path id='{region_obj.id}' class='region' data-node-id='{region_obj.node_id}' "
        f"d='{' '.join(commands)}' fill='{fill}' stroke='{stroke}'{fill_opacity}{fill_rule} />"
    )




def _render_panel_arrow_template(
    region_obj: RegionObject,
    bbox: list[int],
    fill: str,
    stroke: str,
    fill_opacity: str,
) -> str:
    path_data = region_obj.outer_path
    if not path_data:
        x1, y1, x2, y2 = bbox
        mid_y = (y1 + y2) / 2.0
        shoulder = max((y2 - y1) * 0.5, 12.0)
        path_data = (
            f"M {float(x1):.1f} {float(y1):.1f} "
            f"L {float(x2) - shoulder:.1f} {float(y1):.1f} "
            f"L {float(x2):.1f} {mid_y:.1f} "
            f"L {float(x2) - shoulder:.1f} {float(y2):.1f} "
            f"L {float(x1):.1f} {float(y2):.1f} Z"
        )
    return (
        f"<path id='{region_obj.id}' class='region panel-arrow' data-node-id='{region_obj.node_id}' data-shape-type='panel_arrow' "
        f"d='{path_data}' fill='{fill}' stroke='{stroke}'{fill_opacity} />"
    )


def _render_circle_hint_region_object(
    region_obj: RegionObject,
    node_map: dict[str, SceneNode],
    fill: str,
    stroke: str,
    fill_opacity: str,
) -> str | None:
    node = node_map.get(region_obj.node_id)
    if node is None:
        return None
    if node.shape_hint != 'circle':
        return None
    if str(node.component_role or '').find('container_shape') < 0:
        return None
    x1, y1, x2, y2 = node.bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    rx = max((x2 - x1) / 2.0, 1.0)
    ry = max((y2 - y1) / 2.0, 1.0)
    return (
        f"<ellipse id='{region_obj.id}' class='region' data-node-id='{region_obj.node_id}' data-shape-type='ellipse' "
        f"cx='{cx:.1f}' cy='{cy:.1f}' rx='{rx:.1f}' ry='{ry:.1f}' fill='{fill}' stroke='{stroke}'{fill_opacity} />"
    )


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


def _union_bbox(bboxes) -> list[int]:
    items = list(bboxes)
    return [
        min(bbox[0] for bbox in items),
        min(bbox[1] for bbox in items),
        max(bbox[2] for bbox in items),
        max(bbox[3] for bbox in items),
    ]


def _should_skip_background_rectangle(region_obj: RegionObject) -> bool:
    metadata = region_obj.metadata or {}
    if not metadata.get('contains_text') and not metadata.get('is_text_backdrop'):
        return False
    if metadata.get('shape_type') != 'rectangle':
        return False
    fill = (region_obj.fill or '').lower()
    stroke = (region_obj.stroke or '').lower()
    near_white_fill = fill in {'#ffffff', '#fefefe', '#fcfcfc', 'white'}
    near_white_stroke = stroke in {'#ffffff', '#fefefe', '#fcfcfc', 'white', ''}
    high_opacity = region_obj.fill_opacity is None or region_obj.fill_opacity >= 0.9
    return near_white_fill and near_white_stroke and high_opacity


def _is_large_dark_region(
    region_obj: RegionObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> bool:
    fill = (region_obj.fill or '').lower()
    stroke = (region_obj.stroke or '').lower()
    if not _is_dark_color(fill) and not _is_dark_color(stroke):
        return False

    node = node_map.get(region_obj.node_id)
    if node is None:
        return False
    x1, y1, x2, y2 = node.bbox
    area = max(x2 - x1, 1) * max(y2 - y1, 1)
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    return area >= canvas_area * 0.01



def _fragment_has_pure_black_fill(fragment: str) -> bool:
    lowered = fragment.lower()
    return (
        "fill='#000000'" in lowered
        or 'fill="#000000"' in lowered
        or "fill='black'" in lowered
        or 'fill="black"' in lowered
    )
def _should_prune_raster_object(raster_obj: RasterObject) -> bool:
    metadata = raster_obj.metadata or {}
    if metadata.get('shape_hint') != 'raster_candidate':
        return False

    x1, y1, x2, y2 = raster_obj.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    area = width * height
    variance = float(metadata.get('variance') or 0.0)
    slenderness = max(width, height) / max(min(width, height), 1)
    contours = int(metadata.get('contours') or 0)

    if area < 1000:
        return True
    if variance >= 1500.0 and slenderness >= 6.0:
        return True
    if variance >= 1800.0 and contours <= 2 and area < 2500:
        return True
    return False



def _render_raster_template_override(
    raster_obj: RasterObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> str | None:
    template_name = _infer_raster_template_name(raster_obj, scene_graph, node_map)
    if not template_name:
        return None

    x1, y1, x2, y2 = raster_obj.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    node = node_map.get(raster_obj.node_id)
    fill_color = '#e0e0e0'
    if node is not None and node.fill:
        fill_color = node.fill
    elif isinstance(raster_obj.metadata.get('fill'), str) and raster_obj.metadata.get('fill'):
        fill_color = str(raster_obj.metadata.get('fill'))

    template = SVG_TEMPLATES.get(template_name)
    if template is None:
        return None

    svg = template.format(x=x1, y=y1, w=width, h=height, fill=fill_color)
    return (
        f"<g id='{raster_obj.id}' class='svg-template raster-template' data-node-id='{raster_obj.node_id}' "
        f"data-template-name='{template_name}'>{svg}</g>"
    )


def _infer_raster_template_name(
    raster_obj: RasterObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> str | None:
    metadata = raster_obj.metadata or {}
    variance = float(metadata.get('variance') or 0.0)
    shape_hint = str(metadata.get('shape_hint') or '')
    node = node_map.get(raster_obj.node_id)
    if node is not None:
        template_name = extract_template_name(node.component_role)
        if template_name:
            return 'cohort' if template_name == 'standard_node' else template_name
    if shape_hint != 'raster_candidate' and variance < 1200.0:
        return None

    context = _text_context_near_bbox(scene_graph, raster_obj.bbox)
    return infer_template_from_text_context(context)


def _text_context_near_bbox(scene_graph: SceneGraph, bbox: list[int]) -> str:
    x1, y1, x2, y2 = bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    limit = max(64, int(max(width, height) * 0.6))
    nearby: list[str] = []
    for node in scene_graph.nodes:
        if node.type != 'text' or not (node.text_content or '').strip():
            continue
        if _bbox_gap(bbox, node.bbox) <= limit:
            nearby.append(str(node.text_content).lower())
    return ' '.join(nearby)


def _bbox_gap(left: list[int], right: list[int]) -> int:
    horizontal_gap = max(left[0] - right[2], right[0] - left[2], 0)
    vertical_gap = max(left[1] - right[3], right[1] - left[3], 0)
    return max(horizontal_gap, vertical_gap)

def _render_icon_object(icon_obj: IconObject) -> str:
    fill = icon_obj.fill or '#111111'
    fill_rule = icon_obj.fill_rule or 'evenodd'
    return (
        f"<path id='{icon_obj.id}' class='icon-object' data-node-id='{icon_obj.node_id}' "
        f"d='{icon_obj.compound_path}' fill='{fill}' fill-rule='{fill_rule}' stroke='none' />"
    )


def _render_raster_object(raster_obj: RasterObject) -> str:
    x1, y1, x2, y2 = raster_obj.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    return (
        f"<image id='{raster_obj.id}' class='raster-object' data-node-id='{raster_obj.node_id}' "
        f"x='{x1}' y='{y1}' width='{width}' height='{height}' href='{raster_obj.image_href}' xlink:href='{raster_obj.image_href}' />"
    )


def _render_graph_edge(edge: GraphEdge, scene_graph: SceneGraph, node_map: dict[str, SceneNode]) -> list[str]:
    if len(edge.path) < 2:
        return []
    if not edge.source_id and not edge.target_id:
        return []
    if _edge_is_outside_canvas(edge, scene_graph.width, scene_graph.height):
        return []

    path, forced_target_id = _force_snap_edge_endpoint(edge, scene_graph)
    if path is None:
        return []

    stroke = '#555555'
    marker_attr = " marker-end='url(#standard-arrow)'" if _edge_should_use_marker(edge) or forced_target_id is not None else ''
    target_id = forced_target_id or edge.target_id
    common_attrs = (
        f"class='edge' fill='none' stroke='{stroke}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' "
        f"data-source-id='{edge.source_id or ''}' data-target-id='{target_id or ''}' "
        f"data-relation-id='{edge.id}' data-relation-type='connector'{marker_attr}"
    )

    if len(path) == 2:
        start = path[0]
        end = path[-1]
        return [
            f"<line id='{edge.id}' {common_attrs} x1='{start[0]:.1f}' y1='{start[1]:.1f}' x2='{end[0]:.1f}' y2='{end[1]:.1f}' />"
        ]

    points = ' '.join(f"{point[0]:.1f},{point[1]:.1f}" for point in path)
    return [f"<polyline id='{edge.id}' {common_attrs} points='{points}' />"]




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



def _text_overlaps_template_exclusion(text_node: SceneNode, template_bboxes: list[list[int]]) -> bool:
    text_bbox = text_node.bbox
    text_center_y = (text_bbox[1] + text_bbox[3]) / 2.0
    text_center_x = (text_bbox[0] + text_bbox[2]) / 2.0
    axis_like = _is_template_axis_text(text_node.text_content or '')
    for bbox in template_bboxes:
        if _bbox_overlap(text_bbox, bbox) > 0.0:
            return True
        gap = _bbox_gap(text_bbox, bbox)
        if gap <= 15:
            return True
        if axis_like and gap <= 25:
            return True
        if not axis_like:
            continue
        vertically_aligned = (bbox[1] - 25) <= text_center_y <= (bbox[3] + 25)
        horizontally_aligned = (bbox[0] - 25) <= text_center_x <= (bbox[2] + 25)
        left_axis_gap = bbox[0] - text_bbox[2]
        right_axis_gap = text_bbox[0] - bbox[2]
        bottom_axis_gap = text_bbox[1] - bbox[3]
        if vertically_aligned and 0 <= left_axis_gap <= 110:
            return True
        if vertically_aligned and 0 <= right_axis_gap <= 40:
            return True
        if horizontally_aligned and 0 <= bottom_axis_gap <= 40:
            return True
    return False


def _is_template_axis_text(text_content: str) -> bool:
    lowered = text_content.strip().lower()
    if not lowered:
        return False
    if re.fullmatch(r'[\d.\s%+\-]+', lowered):
        return True
    if lowered in {'years', 'year', 'yr', 'yrs', 'months', 'month', 'days', 'day', 'time', 'time (years)'}:
        return True
    compact = re.sub(r'[^a-z0-9]+', ' ', lowered).strip()
    if compact and any(char.isdigit() for char in compact):
        tokens = [token for token in compact.split() if token]
        long_alpha_tokens = [token for token in tokens if token.isalpha() and len(token) >= 3]
        alpha_count = sum(1 for char in compact if char.isalpha())
        if not long_alpha_tokens and alpha_count <= 3:
            return True
    return False


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



def _text_overlap_score(left: list[int], right: list[int]) -> float:
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
    return max(intersection / left_area, intersection / right_area, intersection / max(union, 1))


def _force_snap_edge_endpoint(edge: GraphEdge, scene_graph: SceneGraph) -> tuple[list[list[float]] | None, str | None]:
    path = [point[:] for point in edge.path]
    if len(path) < 2:
        return None, None
    last_point = path[-1]
    nearest = _nearest_terminal_anchor(last_point, scene_graph)
    if nearest is None:
        return path, None
    anchor_id, anchor_bbox = nearest
    path[-1] = _nearest_bbox_boundary_point(last_point, anchor_bbox)
    return path, anchor_id


def _nearest_terminal_anchor(point: list[float], scene_graph: SceneGraph) -> tuple[str, list[int]] | None:
    candidates: list[tuple[float, float, str, list[int]]] = []
    for node in scene_graph.nodes:
        if node.type == 'text' and (node.text_content or '').strip():
            gap = _point_to_bbox_gap(point, node.bbox)
            if gap <= 40.0:
                center = _bbox_center(node.bbox)
                center_distance = math.hypot(point[0] - center[0], point[1] - center[1])
                candidates.append((gap, center_distance, node.id, node.bbox[:]))
        elif node.type == 'region' and node.shape_hint == 'svg_template':
            gap = _point_to_bbox_gap(point, node.bbox)
            if gap <= 40.0:
                center = _bbox_center(node.bbox)
                center_distance = math.hypot(point[0] - center[0], point[1] - center[1])
                candidates.append((gap, center_distance, node.id, node.bbox[:]))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2], candidates[0][3]


def _bbox_center(bbox: list[int]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _point_to_bbox_gap(point: list[float], bbox: list[int]) -> float:
    dx = max(float(bbox[0]) - float(point[0]), 0.0, float(point[0]) - float(bbox[2]))
    dy = max(float(bbox[1]) - float(point[1]), 0.0, float(point[1]) - float(bbox[3]))
    return math.hypot(dx, dy)


def _nearest_bbox_boundary_point(point: list[float], bbox: list[int]) -> list[float]:
    x = min(max(float(point[0]), float(bbox[0])), float(bbox[2]))
    y = min(max(float(point[1]), float(bbox[1])), float(bbox[3]))
    candidates = [
        (abs(x - float(bbox[0])), [float(bbox[0]), y]),
        (abs(x - float(bbox[2])), [float(bbox[2]), y]),
        (abs(y - float(bbox[1])), [x, float(bbox[1])]),
        (abs(y - float(bbox[3])), [x, float(bbox[3])]),
    ]
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _edge_is_outside_canvas(edge: GraphEdge, canvas_width: int, canvas_height: int, margin: float = 6.0) -> bool:
    xs = [point[0] for point in edge.path]
    ys = [point[1] for point in edge.path]
    return max(xs) < -margin or min(xs) > canvas_width + margin or max(ys) < -margin or min(ys) > canvas_height + margin


def _edge_should_use_marker(edge: GraphEdge) -> bool:
    return edge.arrow_head is not None and _is_reasonable_arrow_head(edge)



def _is_reasonable_arrow_head(edge: GraphEdge) -> bool:
    if not edge.arrow_head or len(edge.path) < 2:
        return False
    tip = edge.arrow_head.get('tip')
    left = edge.arrow_head.get('left')
    right = edge.arrow_head.get('right')
    if tip is None or left is None or right is None:
        return False

    xs = [point[0] for point in edge.path]
    ys = [point[1] for point in edge.path]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    path_length = sum(
        math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        for prev, curr in zip(edge.path, edge.path[1:])
    )
    if path_length <= 0.0:
        return False

    arrow_points = [tip, left, right]
    margin = max(24.0, path_length * 0.75)
    for point in arrow_points:
        if point[0] < min_x - margin or point[0] > max_x + margin:
            return False
        if point[1] < min_y - margin or point[1] > max_y + margin:
            return False

    side_lengths = [
        math.hypot(tip[0] - left[0], tip[1] - left[1]),
        math.hypot(tip[0] - right[0], tip[1] - right[1]),
        math.hypot(left[0] - right[0], left[1] - right[1]),
    ]
    if any(length > max(120.0, path_length * 0.6) for length in side_lengths):
        return False

    arrow_area = abs(
        tip[0] * (left[1] - right[1])
        + left[0] * (right[1] - tip[1])
        + right[0] * (tip[1] - left[1])
    ) / 2.0
    path_span = max(max_x - min_x, max_y - min_y, path_length, 1.0)
    if arrow_area > max(400.0, (path_span * path_span) * 0.2):
        return False
    return True



def _render_node_object(node_obj: NodeObject) -> str:
    fill = node_obj.fill or '#ffffff'
    shape_type = str(node_obj.metadata.get('shape_type') or 'circle')
    if shape_type in {'triangle', 'pentagon'}:
        points = _regular_polygon_points(node_obj, 3 if shape_type == 'triangle' else 5)
        return (
            f"<polygon id='{node_obj.id}' class='node' data-node-id='{node_obj.node_id}' "
            f"data-shape-type='{shape_type}' points='{points}' fill='{fill}' stroke='#000000' />"
        )
    return (
        f"<circle id='{node_obj.id}' class='node' data-node-id='{node_obj.node_id}' "
        f"data-shape-type='circle' cx='{node_obj.center[0]:.1f}' cy='{node_obj.center[1]:.1f}' r='{node_obj.radius:.1f}' "
        f"fill='{fill}' stroke='#000000' />"
    )


def _regular_polygon_points(node_obj: NodeObject, sides: int) -> str:
    angle_offset = _shape_angle_offset(node_obj, sides)
    points: list[str] = []
    for index in range(sides):
        angle = angle_offset + (2.0 * math.pi * index / sides)
        x = node_obj.center[0] + math.cos(angle) * node_obj.radius
        y = node_obj.center[1] + math.sin(angle) * node_obj.radius
        points.append(f'{x:.1f},{y:.1f}')
    return ' '.join(points)


def _shape_angle_offset(node_obj: NodeObject, sides: int) -> float:
    orientation = node_obj.metadata.get('orientation') or {}
    angle_degrees = orientation.get('angle_degrees')
    if isinstance(angle_degrees, (int, float)):
        return math.radians(float(angle_degrees))
    if sides == 3:
        return math.radians(-90.0)
    return math.radians(-90.0)


def _text_nodes(scene_graph: SceneGraph) -> list[SceneNode]:
    return [
        node
        for node in scene_graph.nodes
        if node.type == 'text' and (node.text_content or '').strip()
    ]


def _render_text_node(node: SceneNode) -> str | None:
    if not node.text_content:
        return None
    x1, y1, _x2, y2 = node.bbox
    font_size = max(y2 - y1 - 4, 10)
    baseline_y = y2
    lines = [line for line in node.text_content.splitlines() if line.strip()]
    if len(lines) <= 1:
        return (
            f"<text id='{node.id}' class='text' x='{x1}' y='{baseline_y}' "
            f"font-family='Arial' font-size='{font_size}' fill='{node.stroke or '#000000'}'>"
            f"{escape(node.text_content)}</text>"
        )
    line_height = max((y2 - y1) / max(len(lines), 1), font_size * 0.95)
    first_baseline = y1 + line_height
    tspans = [f"<tspan x='{x1}' y='{first_baseline:.1f}'>{escape(lines[0])}</tspan>"]
    for line in lines[1:]:
        tspans.append(f"<tspan x='{x1}' dy='{line_height:.1f}'>{escape(line)}</tspan>")
    return (
        f"<text id='{node.id}' class='text' x='{x1}' y='{baseline_y}' "
        f"font-family='Arial' font-size='{font_size}' fill='{node.stroke or '#000000'}'>"
        f"{''.join(tspans)}</text>"
    )



