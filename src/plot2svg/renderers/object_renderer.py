"""Object, raster, and node SVG rendering helpers."""

from __future__ import annotations

import math

from ..scene_graph import IconObject, NodeObject, RasterObject, SceneGraph, SceneNode
from ..svg_templates import SVG_TEMPLATES, extract_template_name, infer_template_from_text_context
from .common import bbox_gap


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


def render_raster_template_override(
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
        if bbox_gap(bbox, node.bbox) <= limit:
            nearby.append(str(node.text_content).lower())
    return ' '.join(nearby)


def render_icon_object(icon_obj: IconObject) -> str:
    fill = icon_obj.fill or '#111111'
    fill_rule = icon_obj.fill_rule or 'evenodd'
    return (
        f"<path id='{icon_obj.id}' class='icon-object' data-node-id='{icon_obj.node_id}' "
        f"d='{icon_obj.compound_path}' fill='{fill}' fill-rule='{fill_rule}' stroke='none' />"
    )


def render_raster_object(raster_obj: RasterObject) -> str:
    x1, y1, x2, y2 = raster_obj.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    return (
        f"<image id='{raster_obj.id}' class='raster-object' data-node-id='{raster_obj.node_id}' "
        f"x='{x1}' y='{y1}' width='{width}' height='{height}' href='{raster_obj.image_href}' xlink:href='{raster_obj.image_href}' />"
    )


def render_node_object(node_obj: NodeObject) -> str:
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
