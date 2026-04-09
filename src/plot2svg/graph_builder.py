"""Reconstruct graph topology from nodes and stroke primitives."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .config import PipelineConfig, ThresholdConfig
from .router import FlowchartRouter
from .scene_graph import GraphEdge, SceneGraph, SceneRelation, StrokePrimitive


@dataclass(slots=True)
class _Anchor:
    id: str
    kind: str
    center: list[float]
    radius: float
    bbox: list[float]


def build_graph(scene_graph: SceneGraph, cfg: PipelineConfig | None = None) -> SceneGraph:
    """Attach stroke endpoints to nearby anchors and synthesize connector relations."""

    absorbed_region_ids = {
        region_id
        for primitive in scene_graph.stroke_primitives
        for region_id in primitive.metadata.get('absorbed_region_ids', [])
    }
    object_node_ids = {obj.id: set(obj.node_ids) for obj in scene_graph.objects}
    anchors = _build_anchors(scene_graph, absorbed_region_ids, include_icon_objects=True)
    supplemental_anchors = _build_anchors(
        scene_graph,
        absorbed_region_ids,
        include_object_types={'network_container', 'text_cluster'},
        include_text_nodes=True,
        include_template_nodes=True,
        include_icon_objects=True,
    )
    edges: list[GraphEdge] = []
    thresholds = _graph_thresholds(cfg)
    for primitive in scene_graph.stroke_primitives:
        if len(primitive.points) < 2:
            continue
        if _is_monster_stroke_primitive(primitive, scene_graph.width, scene_graph.height, thresholds):
            continue
        edge_path = [point[:] for point in primitive.points]
        source = _anchor_for_endpoint(edge_path, endpoint_index=0, anchors=anchors, exclude_id=None)
        target = _anchor_for_endpoint(
            edge_path,
            endpoint_index=-1,
            anchors=anchors,
            exclude_id=source.id if source is not None else None,
        )
        source, target = _repair_partial_edge_anchors(edge_path, source, target, supplemental_anchors)
        if _should_drop_weak_one_sided_edge(edge_path, source, target, supplemental_anchors):
            continue
        if _should_drop_partial_edge(edge_path, source, target):
            continue
        if _should_drop_overlapping_semantic_edge(source, target, object_node_ids):
            continue
        if _should_drop_adjacent_text_cluster_link(source, target, primitive):
            continue
        edge_path = _snap_edge_path_to_anchors(edge_path, source, target)
        edge_path, route_degraded = _route_edge_path(edge_path, source, target, scene_graph, primitive)
        edge_path, border_degraded = _degrade_failed_route(edge_path, source, target, scene_graph.width, scene_graph.height)
        route_degraded = route_degraded or border_degraded
        edges.append(
            GraphEdge(
                id=f'graph-edge-{primitive.id}',
                source_id=source.id if source is not None else None,
                target_id=target.id if target is not None else None,
                source_kind=source.kind if source is not None else None,
                target_kind=target.kind if target is not None else None,
                path=edge_path,
                backbone_id=primitive.node_id,
                arrow_head=primitive.arrow_head,
                metadata={
                    **primitive.metadata,
                    'source': 'graph_builder',
                    'primitive_id': primitive.id,
                    'route_degraded': route_degraded,
                },
            )
        )

    edges = _dedupe_graph_edges(edges)
    relations = _append_connector_relations(scene_graph.relations, edges)
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=scene_graph.nodes[:],
        groups=scene_graph.groups[:],
        relations=relations,
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=edges,
    )


def _build_anchors(
    scene_graph: SceneGraph,
    absorbed_region_ids: set[str],
    include_object_types: set[str] | None = None,
    include_text_nodes: bool = False,
    include_template_nodes: bool = False,
    include_icon_objects: bool = False,
) -> list[_Anchor]:
    anchors: list[_Anchor] = []
    for node_obj in scene_graph.node_objects:
        if node_obj.node_id in absorbed_region_ids:
            continue
        radius = max(node_obj.radius, 8.0)
        anchors.append(
            _Anchor(
                id=node_obj.id,
                kind='node',
                center=node_obj.center[:],
                radius=radius,
                bbox=[
                    node_obj.center[0] - radius,
                    node_obj.center[1] - radius,
                    node_obj.center[0] + radius,
                    node_obj.center[1] + radius,
                ],
            )
        )
    object_types = include_object_types or {'label_box', 'title', 'text_cluster'}
    for obj in scene_graph.objects:
        if obj.object_type not in object_types:
            continue
        x1, y1, x2, y2 = obj.bbox
        anchors.append(
            _Anchor(
                id=obj.id,
                kind=obj.object_type,
                center=[(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                radius=max(max(x2 - x1, y2 - y1) / 2.0, 18.0),
                bbox=[float(x1), float(y1), float(x2), float(y2)],
            )
        )
    if include_text_nodes:
        for node in scene_graph.nodes:
            if node.type != 'text' or not (node.text_content or '').strip():
                continue
            x1, y1, x2, y2 = node.bbox
            anchors.append(
                _Anchor(
                    id=node.id,
                    kind='text',
                    center=[(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                    radius=max(max(x2 - x1, y2 - y1) / 2.0, 12.0),
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                )
            )
    if include_template_nodes:
        for node in scene_graph.nodes:
            if node.type != 'region' or node.shape_hint != 'svg_template':
                continue
            x1, y1, x2, y2 = node.bbox
            anchors.append(
                _Anchor(
                    id=node.id,
                    kind='svg_template',
                    center=[(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                    radius=max(max(x2 - x1, y2 - y1) / 2.0, 18.0),
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                )
            )
    if include_icon_objects:
        for icon_obj in scene_graph.icon_objects:
            x1, y1, x2, y2 = icon_obj.bbox
            anchors.append(
                _Anchor(
                    id=icon_obj.id,
                    kind='icon',
                    center=[(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                    radius=max(max(x2 - x1, y2 - y1) / 2.0, 16.0),
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                )
            )
    return anchors


def _graph_thresholds(cfg: PipelineConfig | None) -> ThresholdConfig:
    if cfg is not None and cfg.thresholds is not None:
        return cfg.thresholds
    return ThresholdConfig()


def _is_monster_stroke_primitive(
    primitive: StrokePrimitive,
    canvas_width: int,
    canvas_height: int,
    thresholds: ThresholdConfig,
) -> bool:
    if primitive.metadata.get('shape_hint') == 'panel_arrow':
        return False
    xs = [point[0] for point in primitive.points]
    ys = [point[1] for point in primitive.points]
    bbox_w = max(xs) - min(xs)
    bbox_h = max(ys) - min(ys)
    bbox_area = max(bbox_w, 1.0) * max(bbox_h, 1.0)
    canvas_area = max(float(canvas_width * canvas_height), 1.0)
    bbox_diagonal = math.hypot(bbox_w, bbox_h)
    canvas_diagonal = math.hypot(float(canvas_width), float(canvas_height))
    if primitive.width > thresholds.graph_monster_stroke_width and bbox_area > canvas_area * thresholds.graph_monster_stroke_wide_area_ratio:
        return True
    if bbox_area > canvas_area * thresholds.graph_monster_stroke_area_ratio:
        return True
    if bbox_diagonal > canvas_diagonal * thresholds.graph_monster_stroke_diagonal_ratio and primitive.width > thresholds.graph_monster_stroke_diagonal_width:
        return True
    if primitive.width > thresholds.graph_monster_stroke_width:
        return True
    return False


def _anchor_for_endpoint(
    points: list[list[float]],
    endpoint_index: int,
    anchors: list[_Anchor],
    exclude_id: str | None,
) -> _Anchor | None:
    point = points[endpoint_index]
    reference_point: list[float] | None = None
    if len(points) >= 2:
        reference_point = points[1] if endpoint_index == 0 else points[-2]
    return _nearest_anchor(point, anchors, exclude_id, reference_point)


def _repair_partial_edge_anchors(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
    supplemental_anchors: list[_Anchor],
) -> tuple[_Anchor | None, _Anchor | None]:
    if source is not None and target is not None:
        return source, target
    if _path_length(points) < 60.0:
        return source, target
    if source is None:
        source = _anchor_for_endpoint(
            points,
            endpoint_index=0,
            anchors=supplemental_anchors,
            exclude_id=target.id if target is not None else None,
        )
    if target is None:
        target = _anchor_for_endpoint(
            points,
            endpoint_index=-1,
            anchors=supplemental_anchors,
            exclude_id=source.id if source is not None else None,
        )
    return source, target


def _should_drop_partial_edge(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
) -> bool:
    path_length = _path_length(points)
    if source is not None and target is not None:
        return source.id == target.id
    if source is None and target is None:
        return path_length < 90.0
    anchor = source or target
    unresolved_point = points[-1] if source is not None and target is None else points[0]
    if anchor is not None and _point_to_bbox_gap(unresolved_point, anchor.bbox) <= 80.0:
        return True
    if anchor is None:
        return path_length < 110.0
    if anchor.kind in {'text', 'icon', 'svg_template'}:
        return False
    return path_length < 110.0



def _should_drop_overlapping_semantic_edge(
    source: _Anchor | None,
    target: _Anchor | None,
    object_node_ids: dict[str, set[str]],
) -> bool:
    if source is None or target is None:
        return False
    source_nodes = object_node_ids.get(source.id)
    target_nodes = object_node_ids.get(target.id)
    if not source_nodes or not target_nodes:
        return False
    return bool(source_nodes & target_nodes)


def _should_drop_adjacent_text_cluster_link(
    source: _Anchor | None,
    target: _Anchor | None,
    primitive: StrokePrimitive,
) -> bool:
    if source is None or target is None:
        return False
    if source.kind != 'text_cluster' or target.kind != 'text_cluster':
        return False
    if primitive.arrow_head is not None:
        return False
    horizontal_overlap = _interval_overlap(source.bbox[0], source.bbox[2], target.bbox[0], target.bbox[2])
    min_width = max(min(source.bbox[2] - source.bbox[0], target.bbox[2] - target.bbox[0]), 1.0)
    if horizontal_overlap / min_width < 0.55:
        return False
    vertical_gap = _interval_gap(source.bbox[1], source.bbox[3], target.bbox[1], target.bbox[3])
    return vertical_gap <= 24.0


def _interval_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(min(end_a, end_b) - max(start_a, start_b), 0.0)


def _interval_gap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(start_a - end_b, start_b - end_a, 0.0)


def _should_drop_weak_one_sided_edge(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
    anchors: list[_Anchor],
) -> bool:
    if (source is None) == (target is None):
        return False
    anchored = source or target
    if anchored is None or anchored.kind not in {'text', 'title'}:
        return False
    free_point = points[0] if source is None else points[-1]
    nearest_gap = min((_point_to_bbox_gap(free_point, anchor.bbox) for anchor in anchors if anchor.id != anchored.id), default=float('inf'))
    return nearest_gap > 80.0 and _path_length(points) > 180.0


def _path_length(points: list[list[float]]) -> float:
    length = 0.0
    for left, right in zip(points, points[1:]):
        length += math.hypot(right[0] - left[0], right[1] - left[1])
    return length


def _nearest_anchor(
    point: list[float],
    anchors: list[_Anchor],
    exclude_id: str | None,
    reference_point: list[float] | None,
) -> _Anchor | None:
    candidates: list[tuple[float, _Anchor]] = []
    for anchor in anchors:
        if exclude_id is not None and anchor.id == exclude_id:
            continue
        dx = point[0] - anchor.center[0]
        dy = point[1] - anchor.center[1]
        distance = math.hypot(dx, dy)
        if distance <= _direct_snap_limit(anchor):
            candidates.append((distance, anchor))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    gap_candidates: list[tuple[float, _Anchor]] = []
    for anchor in anchors:
        if exclude_id is not None and anchor.id == exclude_id:
            continue
        gap = _point_to_bbox_gap(point, anchor.bbox)
        if gap > _gap_snap_limit(anchor):
            continue
        center_distance = math.hypot(point[0] - anchor.center[0], point[1] - anchor.center[1])
        gap_candidates.append((gap + center_distance * 0.03, anchor))
    if gap_candidates:
        gap_candidates.sort(key=lambda item: item[0])
        return gap_candidates[0][1]

    if reference_point is None:
        return None

    directional_candidates: list[tuple[float, _Anchor]] = []
    for anchor in anchors:
        if exclude_id is not None and anchor.id == exclude_id:
            continue
        score = _directional_snap_score(point, reference_point, anchor)
        if score is None:
            continue
        directional_candidates.append((score, anchor))
    if directional_candidates:
        directional_candidates.sort(key=lambda item: item[0])
        return directional_candidates[0][1]
    return _ray_extended_anchor(point, reference_point, anchors, exclude_id)


def _direct_snap_limit(anchor: _Anchor) -> float:
    if anchor.kind == 'node':
        return max(anchor.radius * 2.2, 24.0)
    return max(anchor.radius * 1.1, 48.0)


def _gap_snap_limit(anchor: _Anchor) -> float:
    if anchor.kind == 'node':
        return max(anchor.radius * 1.5, 16.0)
    if anchor.kind in {'text', 'title'}:
        return max(min(anchor.radius * 0.45, 28.0), 14.0)
    return max(min(anchor.radius * 0.28, 44.0), 18.0)


def _directional_snap_score(
    point: list[float],
    reference_point: list[float],
    anchor: _Anchor,
) -> float | None:
    direction_x = point[0] - reference_point[0]
    direction_y = point[1] - reference_point[1]
    direction_norm = math.hypot(direction_x, direction_y)
    if direction_norm <= 1e-6:
        return None
    direction_x /= direction_norm
    direction_y /= direction_norm

    to_anchor_x = anchor.center[0] - point[0]
    to_anchor_y = anchor.center[1] - point[1]
    center_distance = math.hypot(to_anchor_x, to_anchor_y)
    if center_distance <= 1e-6:
        return 0.0
    unit_x = to_anchor_x / center_distance
    unit_y = to_anchor_y / center_distance
    alignment = direction_x * unit_x + direction_y * unit_y
    if alignment < 0.72:
        return None

    gap = _point_to_bbox_gap(point, anchor.bbox)
    if anchor.kind == 'node':
        hard_cap = max(anchor.radius * 3.2, 42.0)
        if alignment >= 0.9:
            hard_cap = max(anchor.radius * 8.0, 96.0)
    else:
        hard_cap = max(anchor.radius * 1.8, 60.0)
        if alignment >= 0.92:
            hard_cap = max(anchor.radius * 2.4, 72.0)
    if gap > hard_cap:
        return None

    lateral = abs(direction_x * to_anchor_y - direction_y * to_anchor_x)
    lateral_cap = max(anchor.radius * 2.4, 22.0) if anchor.kind == 'node' else max(anchor.radius * 2.6, 36.0)
    if lateral > lateral_cap:
        return None

    return gap + center_distance * 0.05 - alignment * 10.0


def _point_to_bbox_gap(point: list[float], bbox: list[float]) -> float:
    x = float(point[0])
    y = float(point[1])
    dx = max(float(bbox[0]) - x, 0.0, x - float(bbox[2]))
    dy = max(float(bbox[1]) - y, 0.0, y - float(bbox[3]))
    return math.hypot(dx, dy)


def _ray_extended_anchor(
    point: list[float],
    reference_point: list[float],
    anchors: list[_Anchor],
    exclude_id: str | None,
) -> _Anchor | None:
    direction_x = point[0] - reference_point[0]
    direction_y = point[1] - reference_point[1]
    direction_norm = math.hypot(direction_x, direction_y)
    if direction_norm <= 1e-6:
        return None
    direction_x /= direction_norm
    direction_y /= direction_norm

    candidates: list[tuple[float, _Anchor]] = []
    for anchor in anchors:
        if exclude_id is not None and anchor.id == exclude_id:
            continue
        distance = _ray_bbox_intersection_distance(point, [direction_x, direction_y], anchor.bbox)
        if distance is None or distance > _ray_extension_limit(anchor):
            continue
        candidates.append((distance, anchor))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _ray_extension_limit(anchor: _Anchor) -> float:
    if anchor.kind == 'node':
        return max(anchor.radius * 2.0, 30.0)
    if anchor.kind in {'text', 'svg_template'}:
        return 52.0
    return max(min(anchor.radius * 0.35, 54.0), 36.0)


def _ray_bbox_intersection_distance(
    point: list[float],
    direction: list[float],
    bbox: list[float],
) -> float | None:
    x = float(point[0])
    y = float(point[1])
    dx = float(direction[0])
    dy = float(direction[1])
    t_min = 0.0
    t_max = float('inf')
    bounds = ((float(bbox[0]), float(bbox[2])), (float(bbox[1]), float(bbox[3])))
    values = ((x, dx), (y, dy))
    for (lower, upper), (origin, delta) in zip(bounds, values):
        if abs(delta) <= 1e-6:
            if origin < lower or origin > upper:
                return None
            continue
        inv_delta = 1.0 / delta
        t1 = (lower - origin) * inv_delta
        t2 = (upper - origin) * inv_delta
        t_enter = min(t1, t2)
        t_exit = max(t1, t2)
        t_min = max(t_min, t_enter)
        t_max = min(t_max, t_exit)
        if t_min > t_max:
            return None
    if t_max < 0.0:
        return None
    if t_min >= 0.0:
        return t_min
    return 0.0


def _snap_edge_path_to_anchors(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
) -> list[list[float]]:
    snapped = [point[:] for point in points]
    if source is not None and len(snapped) >= 2:
        snapped[0] = _snap_endpoint_to_anchor(snapped[0], snapped[1], source)
    if target is not None and len(snapped) >= 2:
        snapped[-1] = _snap_endpoint_to_anchor(snapped[-1], snapped[-2], target)
    return snapped


def _route_edge_path(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
    scene_graph: SceneGraph,
    primitive: StrokePrimitive,
) -> tuple[list[list[float]], bool]:
    if source is None or target is None or len(points) < 2:
        return points, False
    if not _is_semantic_connector_primitive(primitive, scene_graph, source, target):
        return points, False

    exclude_ids = {source.id, target.id}
    exclude_node_ids = _anchor_excluded_node_ids(scene_graph, source, target)
    routed_points = _attempt_orthogonal_route(scene_graph, points[0], points[-1], exclude_ids, exclude_node_ids, relaxed=False)
    if routed_points is None:
        routed_points = _attempt_orthogonal_route(scene_graph, points[0], points[-1], exclude_ids, exclude_node_ids, relaxed=True)
    if routed_points is None:
        return _force_manhattan_path(points[0], points[-1]), False
    return routed_points, False


def _route_grid_size(canvas_width: int, canvas_height: int) -> int:
    max_dim = max(canvas_width, canvas_height)
    if max_dim >= 1200:
        return 10
    return 8


def _attempt_orthogonal_route(
    scene_graph: SceneGraph,
    start: list[float],
    end: list[float],
    exclude_ids: set[str],
    exclude_node_ids: set[str],
    relaxed: bool,
) -> list[list[float]] | None:
    grid_size = _route_grid_size(scene_graph.width, scene_graph.height)
    if relaxed:
        grid_size = max(grid_size - 2, 6)
    router = FlowchartRouter(scene_graph.width, scene_graph.height, grid_size=grid_size)
    _populate_router_obstacles(
        router,
        scene_graph,
        exclude_ids=exclude_ids,
        exclude_node_ids=exclude_node_ids,
        relaxed=relaxed,
    )
    return router.find_orthogonal_path(start, end)


def _is_semantic_connector_primitive(
    primitive: StrokePrimitive,
    scene_graph: SceneGraph,
    source: _Anchor | None,
    target: _Anchor | None,
) -> bool:
    explicit = primitive.metadata.get('semantic_connector')
    if explicit is not None:
        return bool(explicit)
    if primitive.arrow_head is not None:
        return True
    if primitive.metadata.get('shape_hint') == 'panel_arrow':
        return True
    node = next((item for item in scene_graph.nodes if item.id == primitive.node_id), None)
    roles = set(str(node.component_role or '').split('|')) if node is not None else set()
    if 'connector_path' in roles:
        return True
    return source is not None and target is not None and source.id != target.id


def _anchor_excluded_node_ids(
    scene_graph: SceneGraph,
    source: _Anchor,
    target: _Anchor,
) -> set[str]:
    object_node_ids = {obj.id: set(obj.node_ids) for obj in scene_graph.objects}
    excluded: set[str] = set()
    excluded.update(object_node_ids.get(source.id, set()))
    excluded.update(object_node_ids.get(target.id, set()))
    return excluded


def _populate_router_obstacles(
    router: FlowchartRouter,
    scene_graph: SceneGraph,
    exclude_ids: set[str],
    exclude_node_ids: set[str] | None = None,
    relaxed: bool = False,
) -> None:
    text_padding = 0 if relaxed else 20
    shape_padding = 0 if relaxed else 12
    excluded_nodes = exclude_node_ids or set()
    for node in scene_graph.nodes:
        if node.id in exclude_ids or node.id in excluded_nodes:
            continue
        if node.type == 'text' and (node.text_content or '').strip():
            router.add_obstacle(node.bbox, padding=text_padding)
            continue
        if node.type == 'region' and node.shape_hint == 'svg_template':
            router.add_obstacle(node.bbox, padding=shape_padding)
    for icon_obj in scene_graph.icon_objects:
        if icon_obj.id in exclude_ids or icon_obj.node_id in exclude_ids:
            continue
        router.add_obstacle(icon_obj.bbox, padding=shape_padding)


def _force_manhattan_path(start: list[float], end: list[float]) -> list[list[float]]:
    start_pt = [float(start[0]), float(start[1])]
    end_pt = [float(end[0]), float(end[1])]
    if abs(start_pt[0] - end_pt[0]) <= 1e-6 or abs(start_pt[1] - end_pt[1]) <= 1e-6:
        return [start_pt, end_pt]
    if abs(end_pt[1] - start_pt[1]) >= abs(end_pt[0] - start_pt[0]):
        return [start_pt, [start_pt[0], end_pt[1]], end_pt]
    return [start_pt, [end_pt[0], start_pt[1]], end_pt]


def _degrade_failed_route(
    points: list[list[float]],
    source: _Anchor | None,
    target: _Anchor | None,
    canvas_width: int,
    canvas_height: int,
) -> tuple[list[list[float]], bool]:
    if len(points) <= 2 or source is None or target is None:
        return points, False
    if not _looks_like_failed_border_route(points, canvas_width, canvas_height):
        return points, False
    return _force_manhattan_path(points[0], points[-1]), False


def _looks_like_failed_border_route(
    points: list[list[float]],
    canvas_width: int,
    canvas_height: int,
) -> bool:
    if len(points) <= 2:
        return False
    border_margin = 16.0
    border_points = [
        point for point in points[1:-1]
        if point[0] <= border_margin
        or point[1] <= border_margin
        or point[0] >= canvas_width - border_margin
        or point[1] >= canvas_height - border_margin
    ]
    if len(border_points) < 2:
        return False

    repeated_bottom_points = sum(1 for point in points[1:-1] if point[1] >= canvas_height - border_margin)
    repeated_top_points = sum(1 for point in points[1:-1] if point[1] <= border_margin)
    repeated_left_points = sum(1 for point in points[1:-1] if point[0] <= border_margin)
    repeated_right_points = sum(1 for point in points[1:-1] if point[0] >= canvas_width - border_margin)
    if max(repeated_bottom_points, repeated_top_points, repeated_left_points, repeated_right_points) >= 3:
        return True

    direct_length = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1])
    if direct_length <= 1.0:
        return False
    path_length = _path_length(points)
    horizontal_span = max(point[0] for point in points) - min(point[0] for point in points)
    vertical_span = max(point[1] for point in points) - min(point[1] for point in points)
    return len(border_points) >= 3 and path_length >= direct_length * 1.08 and horizontal_span >= canvas_width * 0.08 and vertical_span <= canvas_height * 0.25


def _snap_endpoint_to_anchor(
    point: list[float],
    reference_point: list[float],
    anchor: _Anchor,
) -> list[float]:
    if anchor.kind == 'node':
        direction_x = reference_point[0] - anchor.center[0]
        direction_y = reference_point[1] - anchor.center[1]
        direction_norm = math.hypot(direction_x, direction_y)
        if direction_norm <= 1e-6:
            return anchor.center[:]
        scale = anchor.radius / direction_norm
        return [
            anchor.center[0] + direction_x * scale,
            anchor.center[1] + direction_y * scale,
        ]

    boundary_point = _segment_bbox_entry_point(reference_point, anchor.center, anchor.bbox)
    if boundary_point is not None:
        return boundary_point
    return _nearest_point_on_bbox_boundary(point, anchor.bbox)


def _segment_bbox_entry_point(
    start: list[float],
    end: list[float],
    bbox: list[float],
) -> list[float] | None:
    sx = float(start[0])
    sy = float(start[1])
    ex = float(end[0])
    ey = float(end[1])
    dx = ex - sx
    dy = ey - sy
    candidates: list[tuple[float, list[float]]] = []
    if abs(dx) > 1e-6:
        for edge_x in (float(bbox[0]), float(bbox[2])):
            t = (edge_x - sx) / dx
            if 0.0 <= t <= 1.0:
                y = sy + t * dy
                if float(bbox[1]) - 1e-6 <= y <= float(bbox[3]) + 1e-6:
                    candidates.append((t, [edge_x, y]))
    if abs(dy) > 1e-6:
        for edge_y in (float(bbox[1]), float(bbox[3])):
            t = (edge_y - sy) / dy
            if 0.0 <= t <= 1.0:
                x = sx + t * dx
                if float(bbox[0]) - 1e-6 <= x <= float(bbox[2]) + 1e-6:
                    candidates.append((t, [x, edge_y]))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _nearest_point_on_bbox_boundary(point: list[float], bbox: list[float]) -> list[float]:
    x = min(max(float(point[0]), float(bbox[0])), float(bbox[2]))
    y = min(max(float(point[1]), float(bbox[1])), float(bbox[3]))
    distances = [
        (abs(x - float(bbox[0])), [float(bbox[0]), y]),
        (abs(x - float(bbox[2])), [float(bbox[2]), y]),
        (abs(y - float(bbox[1])), [x, float(bbox[1])]),
        (abs(y - float(bbox[3])), [x, float(bbox[3])]),
    ]
    distances.sort(key=lambda item: item[0])
    return distances[0][1]


def _dedupe_graph_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    if len(edges) < 2:
        return edges

    edges = _collapse_degraded_backbone_pair_duplicates(edges)
    ordered_edges = sorted(edges, key=lambda edge: edge.id)
    kept: list[GraphEdge] = []
    for edge in ordered_edges:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(kept)
                if _edges_are_near_duplicates(existing, edge)
            ),
            None,
        )
        if duplicate_index is None:
            kept.append(edge)
            continue
        if _edge_preference_key(edge) < _edge_preference_key(kept[duplicate_index]):
            kept[duplicate_index] = edge
    return kept


def _collapse_degraded_backbone_pair_duplicates(edges: list[GraphEdge]) -> list[GraphEdge]:
    groups: dict[tuple[str | None, str | None, str | None], list[GraphEdge]] = {}
    for edge in edges:
        key = (edge.backbone_id, edge.source_id, edge.target_id)
        groups.setdefault(key, []).append(edge)

    collapsed: list[GraphEdge] = []
    for group in groups.values():
        degraded = [edge for edge in group if edge.metadata.get('route_degraded')]
        healthy = [edge for edge in group if not edge.metadata.get('route_degraded')]
        if healthy and degraded:
            collapsed.extend(sorted(healthy, key=_edge_preference_key))
            continue
        collapsed.extend(group)
    return collapsed


def _edge_preference_key(edge: GraphEdge) -> tuple[int, int, float, str]:
    route_degraded = 1 if edge.metadata.get('route_degraded') else 0
    return (route_degraded, len(edge.path), _path_length(edge.path), edge.id)


def _edges_are_near_duplicates(left: GraphEdge, right: GraphEdge) -> bool:
    if left.source_id != right.source_id or left.target_id != right.target_id:
        return False
    if left.source_id is None or left.target_id is None:
        return False
    if len(left.path) < 2 or len(right.path) < 2:
        return False
    start_close = _point_distance(left.path[0], right.path[0]) <= 12.0
    end_close = _point_distance(left.path[-1], right.path[-1]) <= 40.0
    if not (start_close and end_close):
        return False
    if left.backbone_id == right.backbone_id:
        return bool(left.metadata.get('route_degraded') or right.metadata.get('route_degraded'))
    return _point_distance(_path_bbox_center(left.path), _path_bbox_center(right.path)) <= 30.0


def _path_bbox_center(points: list[list[float]]) -> list[float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [(min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0]


def _point_distance(left: list[float], right: list[float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _append_connector_relations(
    existing_relations: list[SceneRelation],
    edges: list[GraphEdge],
) -> list[SceneRelation]:
    relations = existing_relations[:]
    seen = {
        (relation.relation_type, tuple(relation.source_ids), tuple(relation.target_ids), relation.backbone_id)
        for relation in relations
    }
    for edge in edges:
        if not edge.source_id or not edge.target_id or edge.source_id == edge.target_id:
            continue
        key = ('connector', (edge.source_id,), (edge.target_id,), edge.backbone_id)
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            SceneRelation(
                id=f'relation-{edge.id}',
                relation_type='connector',
                source_ids=[edge.source_id],
                target_ids=[edge.target_id],
                backbone_id=edge.backbone_id,
                metadata={
                    'direction': _infer_relation_direction(edge.path[0], edge.path[-1]),
                    'shape_type': 'connector',
                    'source': 'graph_builder',
                },
            )
        )
    return relations


def _infer_relation_direction(source_point: list[float], target_point: list[float]) -> str:
    sx, sy = source_point
    tx, ty = target_point
    if abs(tx - sx) >= abs(ty - sy):
        return 'right' if tx >= sx else 'left'
    return 'down' if ty >= sy else 'up'
