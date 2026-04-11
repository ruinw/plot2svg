"""Geometric heuristic detectors for box, arrow, and container structures."""

from __future__ import annotations

import statistics

from .config import PipelineConfig, ThresholdConfig
from .scene_graph import (
    SceneGraph,
    SceneGroup,
    SceneNode,
    SceneObject,
    SceneRelation,
    _bbox_area,
    _contains_bbox,
    _union_bboxes,
)
from .svg_templates import append_template_role, extract_template_name


def detect_structures(scene_graph: SceneGraph, cfg: PipelineConfig | None = None) -> SceneGraph:
    """Classify boxes/arrows and detect containers, returning an updated SceneGraph."""

    thresholds = _structure_thresholds(cfg)
    node_map = {node.id: node for node in scene_graph.nodes}
    groups = [_clone_group(g) for g in scene_graph.groups]
    updated_nodes = {node.id: node for node in scene_graph.nodes}
    relations = [_clone_relation(r) for r in scene_graph.relations]
    objects = [_clone_object(o) for o in scene_graph.objects]
    object_type_index = _build_object_type_index(objects)

    groups = _classify_boxes(groups, node_map, object_type_index, thresholds)
    groups = _classify_arrows(groups, node_map, thresholds)
    relations = _detect_connector_relations(groups, node_map, relations, thresholds)
    groups, updated_nodes, relations = _detect_fans(
        groups,
        updated_nodes,
        relations,
        scene_graph.width,
        scene_graph.height,
        thresholds,
    )
    groups, updated_nodes = _detect_containers(
        groups, updated_nodes, scene_graph.width, scene_graph.height,
    )

    ordered_nodes = [updated_nodes[node.id] for node in scene_graph.nodes]
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=ordered_nodes,
        groups=groups,
        relations=relations,
        objects=objects,
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


# ---------------------------------------------------------------------------
# Box classifier
# ---------------------------------------------------------------------------

def _classify_boxes(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
    object_type_index: dict[str, set[str]],
    thresholds: ThresholdConfig,
) -> list[SceneGroup]:
    """Tag labeled_region / labeled_component groups as shape_type='box'."""

    result: list[SceneGroup] = []
    for group in groups:
        if group.role not in ("labeled_region", "labeled_component"):
            result.append(group)
            continue

        region_node = _primary_region(group, node_map)
        has_text = any(
            node_map[cid].type == "text"
            for cid in group.child_ids
            if cid in node_map
        )
        if (
            region_node is not None
            and has_text
            and not (object_type_index.get(region_node.id, set()) & {"network_container", "cluster_region"})
            and _is_box_shape(region_node, thresholds)
        ):
            group.shape_type = "box"
        result.append(group)
    return result


def _primary_region(
    group: SceneGroup,
    node_map: dict[str, SceneNode],
) -> SceneNode | None:
    for cid in group.child_ids:
        node = node_map.get(cid)
        if node is not None and node.type == "region":
            return node
    return None


def _is_box_shape(node: SceneNode, thresholds: ThresholdConfig) -> bool:
    w = max(node.bbox[2] - node.bbox[0], 1)
    h = max(node.bbox[3] - node.bbox[1], 1)
    aspect = max(w / h, h / w)
    return aspect < thresholds.detect_structure_box_aspect_max and min(w, h) >= thresholds.detect_structure_box_min_side


# ---------------------------------------------------------------------------
# Arrow classifier
# ---------------------------------------------------------------------------

def _classify_arrows(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
    thresholds: ThresholdConfig,
) -> list[SceneGroup]:
    """Tag connector groups as shape_type='arrow' with optional direction."""

    result: list[SceneGroup] = []
    for group in groups:
        if group.role != "connector":
            result.append(group)
            continue

        group.shape_type = "arrow"
        w = max(group.bbox[2] - group.bbox[0], 1)
        h = max(group.bbox[3] - group.bbox[1], 1)
        if w >= h * thresholds.detect_structure_arrow_aspect_ratio:
            group.direction = "right"
        elif h >= w * thresholds.detect_structure_arrow_aspect_ratio:
            group.direction = "down"
        result.append(group)
    return result


# ---------------------------------------------------------------------------
# Fan detector
# ---------------------------------------------------------------------------

_FAN_MIN_SOURCE_COUNT = 4
_FAN_MIN_HEIGHT = 180
_FAN_MAX_X_RATIO = 0.25


def _detect_fans(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
    relations: list[SceneRelation],
    canvas_w: int,
    _canvas_h: int,
    thresholds: ThresholdConfig,
) -> tuple[list[SceneGroup], dict[str, SceneNode], list[SceneRelation]]:
    assigned_ids = {cid for group in groups for cid in group.child_ids}
    circle_nodes = [
        node for node in node_map.values()
        if node.type == "region"
        and node.shape_hint == "circle"
        and node.id not in assigned_ids
    ]
    region_nodes = [
        node for node in node_map.values()
        if node.type == "region"
        and node.shape_hint != "circle"
        and node.id not in assigned_ids
        and node.id != "background-root"
    ]
    stroke_nodes = [
        node for node in node_map.values()
        if node.type == "stroke"
        and node.id not in assigned_ids
    ]

    new_groups: list[SceneGroup] = []
    for stroke in stroke_nodes:
        x1, y1, x2, y2 = stroke.bbox
        width = max(x2 - x1, 1)
        height = max(y2 - y1, 1)
        if height < thresholds.detect_structure_fan_min_height or x1 > canvas_w * thresholds.detect_structure_fan_max_x_ratio:
            continue
        if height < width * thresholds.detect_structure_fan_height_width_ratio:
            continue

        sources = [
            node for node in circle_nodes
            if abs(node.bbox[0] - x1) <= thresholds.detect_structure_fan_source_x_tolerance
            and node.bbox[1] >= y1 - thresholds.detect_structure_fan_source_y_margin
            and node.bbox[3] <= y2 + thresholds.detect_structure_fan_source_y_margin
        ]
        if len(sources) < thresholds.detect_structure_fan_min_source_count:
            continue

        target = _find_fan_target(stroke, region_nodes, thresholds)
        if target is None:
            continue

        child_nodes = [stroke, target, *sorted(sources, key=lambda item: item.bbox[1])]
        child_ids = [node.id for node in child_nodes]
        group_id = f"fan-{stroke.id}"
        new_groups.append(
            SceneGroup(
                id=group_id,
                role="fan",
                bbox=_union_bboxes(node.bbox for node in child_nodes),
                child_ids=child_ids,
                shape_type="fan",
            )
        )
        relations.append(
            SceneRelation(
                id=f"relation-{group_id}",
                relation_type="fan",
                source_ids=[node.id for node in sorted(sources, key=lambda item: item.bbox[1])],
                target_ids=[target.id],
                backbone_id=stroke.id,
                group_id=group_id,
                metadata={"direction": "right"},
            )
        )
        for node in child_nodes:
            if node.type == "stroke":
                component_role = "fan_backbone"
            elif node.id == target.id:
                component_role = "fan_target"
            else:
                component_role = "fan_source"
            node_map[node.id] = _with_group_metadata(node, group_id, component_role)
            assigned_ids.add(node.id)
    return groups + new_groups, node_map, relations


def _detect_connector_relations(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
    relations: list[SceneRelation],
    thresholds: ThresholdConfig,
) -> list[SceneRelation]:
    existing_group_ids = {relation.group_id for relation in relations if relation.group_id is not None}
    anchor_nodes = [
        node
        for node in node_map.values()
        if node.type in {"region", "text"}
        and node.id != "background-root"
    ]

    for group in groups:
        if group.role != "connector" or group.id in existing_group_ids:
            continue
        backbone = _primary_stroke(group, node_map)
        if backbone is None:
            continue

        source_point, target_point = _connector_endpoints(group)
        source_node = _nearest_anchor(source_point, anchor_nodes, exclude_ids=set(group.child_ids), thresholds=thresholds)
        target_node = _nearest_anchor(target_point, anchor_nodes, exclude_ids=set(group.child_ids) | ({source_node.id} if source_node else set()), thresholds=thresholds)
        if source_node is None or target_node is None:
            continue

        relations.append(
            SceneRelation(
                id=f"relation-{group.id}",
                relation_type="connector",
                source_ids=[source_node.id],
                target_ids=[target_node.id],
                backbone_id=backbone.id,
                group_id=group.id,
                metadata={
                    "direction": group.direction or _infer_relation_direction(source_point, target_point),
                    "shape_type": group.shape_type or "connector",
                },
            )
        )
    return relations


def _find_fan_target(stroke: SceneNode, region_nodes: list[SceneNode], thresholds: ThresholdConfig) -> SceneNode | None:
    sx1, sy1, sx2, sy2 = stroke.bbox
    candidates: list[tuple[int, int, SceneNode]] = []
    for node in region_nodes:
        x1, y1, x2, y2 = node.bbox
        width = x2 - x1
        height = y2 - y1
        if width < thresholds.detect_structure_fan_target_min_width or height < thresholds.detect_structure_fan_target_min_height:
            continue
        if x1 <= sx2:
            continue
        gap = x1 - sx2
        if gap > thresholds.detect_structure_fan_target_max_gap:
            continue
        overlap_y = max(0, min(sy2, y2) - max(sy1, y1))
        if overlap_y <= 0:
            continue
        area = _bbox_area(node.bbox)
        candidates.append((gap, -area, node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _primary_stroke(group: SceneGroup, node_map: dict[str, SceneNode]) -> SceneNode | None:
    for child_id in group.child_ids:
        node = node_map.get(child_id)
        if node is not None and node.type == "stroke":
            return node
    return None


def _connector_endpoints(group: SceneGroup) -> tuple[tuple[float, float], tuple[float, float]]:
    x1, y1, x2, y2 = group.bbox
    width = x2 - x1
    height = y2 - y1
    if group.direction == "down":
        return ((x1 + x2) / 2.0, float(y1)), ((x1 + x2) / 2.0, float(y2))
    if group.direction == "right" or width >= height:
        return (float(x1), (y1 + y2) / 2.0), (float(x2), (y1 + y2) / 2.0)
    return ((x1 + x2) / 2.0, float(y1)), ((x1 + x2) / 2.0, float(y2))


def _nearest_anchor(
    point: tuple[float, float],
    nodes: list[SceneNode],
    exclude_ids: set[str],
    thresholds: ThresholdConfig,
) -> SceneNode | None:
    candidates: list[tuple[float, int, SceneNode]] = []
    px, py = point
    for node in nodes:
        if node.id in exclude_ids:
            continue
        distance = _point_to_bbox_distance(point, node.bbox)
        if distance > thresholds.detect_structure_connector_anchor_max_distance:
            continue
        candidates.append((distance, -_bbox_area(node.bbox), node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _structure_thresholds(cfg: PipelineConfig | None) -> ThresholdConfig:
    if cfg is not None and cfg.thresholds is not None:
        return cfg.thresholds
    return ThresholdConfig()


def _point_to_bbox_distance(point: tuple[float, float], bbox: list[int]) -> float:
    px, py = point
    x1, y1, x2, y2 = bbox
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return (dx * dx + dy * dy) ** 0.5


def _infer_relation_direction(source_point: tuple[float, float], target_point: tuple[float, float]) -> str:
    sx, sy = source_point
    tx, ty = target_point
    if abs(tx - sx) >= abs(ty - sy):
        return "right" if tx >= sx else "left"
    return "down" if ty >= sy else "up"


# ---------------------------------------------------------------------------
# Container detector
# ---------------------------------------------------------------------------

_CANVAS_AREA_MAX_RATIO = 0.60
_CONTAINER_AREA_MULTIPLIER = 3.0
_CONTAIN_MARGIN = 10
_MIN_CONTAINED_GROUPS = 2


def _detect_containers(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
    canvas_w: int,
    canvas_h: int,
) -> tuple[list[SceneGroup], dict[str, SceneNode]]:
    """Discover container groups from unassigned large region nodes."""

    if not groups:
        return groups, node_map

    canvas_area = max(canvas_w * canvas_h, 1)
    area_cap = canvas_area * _CANVAS_AREA_MAX_RATIO

    assigned_ids = {cid for group in groups for cid in group.child_ids}
    group_areas = [_bbox_area(g.bbox) for g in groups]
    median_area = statistics.median(group_areas) if group_areas else 0

    unassigned_regions = [
        node for node in node_map.values()
        if node.type == "region"
        and node.id not in assigned_ids
        and node.id != "background-root"
    ]

    new_groups: list[SceneGroup] = []
    for region in unassigned_regions:
        region_area = _bbox_area(region.bbox)
        if region_area > area_cap:
            continue
        if median_area > 0 and region_area < median_area * _CONTAINER_AREA_MULTIPLIER:
            continue

        contained_ids: list[str] = []
        for group in groups:
            if _contains_bbox(region.bbox, group.bbox, margin=_CONTAIN_MARGIN):
                contained_ids.append(group.id)
        if len(contained_ids) < _MIN_CONTAINED_GROUPS:
            continue

        group_id = f"container-{region.id}"
        container_group = SceneGroup(
            id=group_id,
            role="container",
            bbox=region.bbox[:],
            child_ids=[region.id],
            shape_type="container",
            contains_group_ids=contained_ids,
        )
        new_groups.append(container_group)

        node_map[region.id] = _with_group_metadata(region, group_id, "container_boundary")

    return groups + new_groups, node_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clone_group(group: SceneGroup) -> SceneGroup:
    return SceneGroup(
        id=group.id,
        role=group.role,
        bbox=group.bbox[:],
        child_ids=group.child_ids[:],
        shape_type=group.shape_type,
        direction=group.direction,
        contains_group_ids=group.contains_group_ids[:],
    )


def _clone_relation(relation: SceneRelation) -> SceneRelation:
    return SceneRelation(
        id=relation.id,
        relation_type=relation.relation_type,
        source_ids=relation.source_ids[:],
        target_ids=relation.target_ids[:],
        backbone_id=relation.backbone_id,
        group_id=relation.group_id,
        metadata=relation.metadata.copy(),
    )


def _clone_object(obj: SceneObject) -> SceneObject:
    return SceneObject(
        id=obj.id,
        object_type=obj.object_type,
        bbox=obj.bbox[:],
        node_ids=obj.node_ids[:],
        group_ids=obj.group_ids[:],
        metadata=obj.metadata.copy(),
    )


def _build_object_type_index(objects: list[SceneObject]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for obj in objects:
        for node_id in obj.node_ids:
            index.setdefault(node_id, set()).add(obj.object_type)
    return index


def _with_group_metadata(node: SceneNode, group_id: str, component_role: str) -> SceneNode:
    merged_role = component_role
    template_name = extract_template_name(node.component_role)
    if template_name:
        merged_role = append_template_role(component_role, template_name)
    return SceneNode(
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
        group_id=group_id,
        component_role=merged_role,
        children=node.children[:],
        shape_hint=node.shape_hint,
    )
