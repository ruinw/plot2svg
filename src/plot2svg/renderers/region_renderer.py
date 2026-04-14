"""Region-object SVG rendering helpers."""

from __future__ import annotations

import math

from ..color_utils import _is_dark_color, _is_pure_black_region_fill
from ..scene_graph import RegionObject, SceneGraph, SceneNode
from ..svg_templates import render_svg_template


def region_sort_key(region_obj: RegionObject, node_map: dict[str, SceneNode]) -> float:
    node = node_map.get(region_obj.node_id)
    if node is not None:
        x1, y1, x2, y2 = node.bbox
        return float(max(x2 - x1, 1) * max(y2 - y1, 1))
    ellipse = region_obj.metadata.get('ellipse') or {}
    if ellipse:
        return math.pi * float(ellipse.get('rx', 0.0)) * float(ellipse.get('ry', 0.0))
    circle = region_obj.metadata.get('circle') or {}
    if circle:
        radius = float(circle.get('r', 0.0))
        return math.pi * radius * radius
    return 0.0


def render_region_object(
    region_obj: RegionObject,
    scene_graph: SceneGraph,
    node_map: dict[str, SceneNode],
) -> str | None:
    if region_obj.metadata.get('entity_valid') is False:
        return None
    if region_obj.metadata.get('shape_type') == 'svg_template':
        template_name = str(region_obj.metadata.get('template_name') or '')
        template_bbox = region_obj.metadata.get('template_bbox') or [0, 0, 1, 1]
        return render_svg_template(
            template_name,
            [int(value) for value in template_bbox],
            element_id=region_obj.id,
            node_id=region_obj.node_id,
            fill=region_obj.fill,
            stroke=region_obj.stroke,
        )
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
