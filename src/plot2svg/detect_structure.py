"""Geometric heuristic detectors for box, arrow, and container structures."""

from __future__ import annotations

import statistics

from .scene_graph import (
    SceneGraph,
    SceneGroup,
    SceneNode,
    _bbox_area,
    _contains_bbox,
    _union_bboxes,
)


def detect_structures(scene_graph: SceneGraph) -> SceneGraph:
    """Classify boxes/arrows and detect containers, returning an updated SceneGraph."""

    node_map = {node.id: node for node in scene_graph.nodes}
    groups = [_clone_group(g) for g in scene_graph.groups]
    updated_nodes = {node.id: node for node in scene_graph.nodes}

    groups = _classify_boxes(groups, node_map)
    groups = _classify_arrows(groups, node_map)
    groups, updated_nodes = _detect_containers(
        groups, updated_nodes, scene_graph.width, scene_graph.height,
    )

    ordered_nodes = [updated_nodes[node.id] for node in scene_graph.nodes]
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=ordered_nodes,
        groups=groups,
    )


# ---------------------------------------------------------------------------
# Box classifier
# ---------------------------------------------------------------------------

def _classify_boxes(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
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
        if region_node is not None and has_text and _is_box_shape(region_node):
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


def _is_box_shape(node: SceneNode) -> bool:
    w = max(node.bbox[2] - node.bbox[0], 1)
    h = max(node.bbox[3] - node.bbox[1], 1)
    aspect = max(w / h, h / w)
    return aspect < 6.0 and min(w, h) >= 20


# ---------------------------------------------------------------------------
# Arrow classifier
# ---------------------------------------------------------------------------

def _classify_arrows(
    groups: list[SceneGroup],
    node_map: dict[str, SceneNode],
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
        if w >= h * 2.0:
            group.direction = "right"
        elif h >= w * 2.0:
            group.direction = "down"
        result.append(group)
    return result


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

        node_map[region.id] = SceneNode(
            id=region.id,
            type=region.type,
            bbox=region.bbox[:],
            z_index=region.z_index,
            vector_mode=region.vector_mode,
            confidence=region.confidence,
            fill=region.fill,
            stroke=region.stroke,
            stroke_width=region.stroke_width,
            source_mask=region.source_mask,
            text_content=region.text_content,
            group_id=group_id,
            component_role="container_boundary",
            children=region.children[:],
        )

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
