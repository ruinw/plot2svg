"""Graph-edge SVG rendering helpers."""

from __future__ import annotations

import math

from ..scene_graph import GraphEdge, SceneGraph, SceneNode
from .common import bbox_center, nearest_bbox_boundary_point, point_to_bbox_gap


def render_graph_edge(edge: GraphEdge, scene_graph: SceneGraph, node_map: dict[str, SceneNode]) -> list[str]:
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


def _force_snap_edge_endpoint(edge: GraphEdge, scene_graph: SceneGraph) -> tuple[list[list[float]] | None, str | None]:
    path = [point[:] for point in edge.path]
    if len(path) < 2:
        return None, None
    last_point = path[-1]
    nearest = _nearest_terminal_anchor(last_point, scene_graph)
    if nearest is None:
        return path, None
    anchor_id, anchor_bbox = nearest
    path[-1] = nearest_bbox_boundary_point(last_point, anchor_bbox)
    return path, anchor_id


def _nearest_terminal_anchor(point: list[float], scene_graph: SceneGraph) -> tuple[str, list[int]] | None:
    candidates: list[tuple[float, float, str, list[int]]] = []
    for node in scene_graph.nodes:
        if node.type == 'text' and (node.text_content or '').strip():
            gap = point_to_bbox_gap(point, node.bbox)
            if gap <= 40.0:
                center = bbox_center(node.bbox)
                center_distance = math.hypot(point[0] - center[0], point[1] - center[1])
                candidates.append((gap, center_distance, node.id, node.bbox[:]))
        elif node.type == 'region' and node.shape_hint == 'svg_template':
            gap = point_to_bbox_gap(point, node.bbox)
            if gap <= 40.0:
                center = bbox_center(node.bbox)
                center_distance = math.hypot(point[0] - center[0], point[1] - center[1])
                candidates.append((gap, center_distance, node.id, node.bbox[:]))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2], candidates[0][3]


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
