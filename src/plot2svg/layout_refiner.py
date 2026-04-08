"""Late-stage layout refinement for text de-confliction and edge sync."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher

from .scene_graph import GraphEdge, SceneGraph, SceneGroup, SceneNode, SceneObject, SceneRelation


def refine_layout(scene_graph: SceneGraph) -> SceneGraph:
    """Merge fuzzy duplicate text nodes, nudge overlaps, and sync edge endpoints."""

    nodes = [replace(node, bbox=node.bbox[:], children=node.children[:]) for node in scene_graph.nodes]
    nodes, remap = _merge_fuzzy_text_duplicates(nodes)
    nodes = _nudge_overlapping_text_nodes(nodes, scene_graph.height)
    node_map = {node.id: node for node in nodes}
    groups = _remap_groups(scene_graph.groups, remap, node_map)
    relations = _remap_relations(scene_graph.relations, remap)
    objects = _remap_objects(scene_graph.objects, remap)
    edges = _sync_graph_edges(scene_graph.graph_edges, remap, node_map)
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=nodes,
        groups=groups,
        relations=relations,
        objects=objects,
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=edges,
    )


def _merge_fuzzy_text_duplicates(nodes: list[SceneNode]) -> tuple[list[SceneNode], dict[str, str]]:
    text_nodes = [node for node in nodes if node.type == 'text' and (node.text_content or '').strip()]
    consumed: set[str] = set()
    replacements: dict[str, str] = {}
    merged_nodes: list[SceneNode] = []
    for node in text_nodes:
        if node.id in consumed:
            continue
        cluster = [node]
        consumed.add(node.id)
        for candidate in text_nodes:
            if candidate.id in consumed:
                continue
            if _bbox_overlap_ratio(node.bbox, candidate.bbox) <= 0.30:
                continue
            if _text_similarity(node.text_content or '', candidate.text_content or '') < 0.82:
                continue
            consumed.add(candidate.id)
            replacements[candidate.id] = node.id
            cluster.append(candidate)
        if len(cluster) == 1:
            merged_nodes.append(node)
            continue
        merged_nodes.append(
            replace(
                node,
                bbox=_union_bbox(item.bbox for item in cluster),
                text_content=max((item.text_content or '' for item in cluster), key=len),
                confidence=max(item.confidence for item in cluster),
            )
        )
    keep_ids = {node.id for node in merged_nodes if node.type == 'text'}
    other_nodes = [node for node in nodes if node.type != 'text' or node.id in keep_ids]
    final_nodes: list[SceneNode] = []
    merged_map = {node.id: node for node in merged_nodes}
    for node in other_nodes:
        if node.type == 'text' and node.id in merged_map:
            final_nodes.append(merged_map[node.id])
        elif node.type != 'text':
            final_nodes.append(node)
    return final_nodes, replacements


def _nudge_overlapping_text_nodes(nodes: list[SceneNode], canvas_height: int) -> list[SceneNode]:
    text_ids = [index for index, node in enumerate(nodes) if node.type == 'text' and (node.text_content or '').strip()]
    for pos, left_index in enumerate(text_ids):
        left = nodes[left_index]
        for right_index in text_ids[pos + 1:]:
            right = nodes[right_index]
            if _bbox_overlap_ratio(left.bbox, right.bbox) <= 0.30:
                continue
            overlap_height = min(left.bbox[3], right.bbox[3]) - max(left.bbox[1], right.bbox[1])
            if overlap_height <= 0:
                continue
            shift = overlap_height + 6
            x1, y1, x2, y2 = right.bbox
            height = y2 - y1
            new_y1 = min(y1 + shift, max(canvas_height - height, 0))
            new_y2 = new_y1 + height
            nodes[right_index] = replace(right, bbox=[x1, new_y1, x2, new_y2])
    return nodes


def _sync_graph_edges(edges: list[GraphEdge], remap: dict[str, str], node_map: dict[str, SceneNode]) -> list[GraphEdge]:
    updated: list[GraphEdge] = []
    for edge in edges:
        source_id = remap.get(edge.source_id, edge.source_id) if edge.source_id is not None else None
        target_id = remap.get(edge.target_id, edge.target_id) if edge.target_id is not None else None
        path = [point[:] for point in edge.path]
        if len(path) >= 2 and source_id in node_map and node_map[source_id].type == 'text':
            path[0] = _nearest_bbox_boundary_point(path[1], node_map[source_id].bbox)
        if len(path) >= 2 and target_id in node_map and node_map[target_id].type == 'text':
            path[-1] = _nearest_bbox_boundary_point(path[-2], node_map[target_id].bbox)
        updated.append(
            GraphEdge(
                id=edge.id,
                source_id=source_id,
                target_id=target_id,
                path=path,
                backbone_id=edge.backbone_id,
                source_kind=edge.source_kind,
                target_kind=edge.target_kind,
                arrow_head=edge.arrow_head,
                metadata=edge.metadata.copy(),
            )
        )
    return updated


def _remap_groups(groups: list[SceneGroup], remap: dict[str, str], node_map: dict[str, SceneNode]) -> list[SceneGroup]:
    updated: list[SceneGroup] = []
    for group in groups:
        child_ids: list[str] = []
        seen: set[str] = set()
        for child_id in group.child_ids:
            mapped = remap.get(child_id, child_id)
            if mapped in seen or mapped not in node_map:
                continue
            seen.add(mapped)
            child_ids.append(mapped)
        bbox = _union_bbox(node_map[child_id].bbox for child_id in child_ids) if child_ids else group.bbox[:]
        updated.append(SceneGroup(id=group.id, role=group.role, bbox=bbox, child_ids=child_ids, shape_type=group.shape_type, direction=group.direction, contains_group_ids=group.contains_group_ids[:]))
    return updated


def _remap_relations(relations: list[SceneRelation], remap: dict[str, str]) -> list[SceneRelation]:
    updated: list[SceneRelation] = []
    for relation in relations:
        updated.append(SceneRelation(id=relation.id, relation_type=relation.relation_type, source_ids=[remap.get(item, item) for item in relation.source_ids], target_ids=[remap.get(item, item) for item in relation.target_ids], backbone_id=relation.backbone_id, group_id=relation.group_id, metadata=relation.metadata.copy()))
    return updated


def _remap_objects(objects: list[SceneObject], remap: dict[str, str]) -> list[SceneObject]:
    updated: list[SceneObject] = []
    for obj in objects:
        seen: set[str] = set()
        node_ids: list[str] = []
        for node_id in obj.node_ids:
            mapped = remap.get(node_id, node_id)
            if mapped in seen:
                continue
            seen.add(mapped)
            node_ids.append(mapped)
        updated.append(SceneObject(id=obj.id, object_type=obj.object_type, bbox=obj.bbox[:], node_ids=node_ids, group_ids=obj.group_ids[:], metadata=obj.metadata.copy()))
    return updated


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _normalize_text(text: str) -> str:
    return ''.join(ch.lower() for ch in text if ch.isalnum() or ch.isspace()).strip()


def _bbox_overlap_ratio(left: list[int], right: list[int]) -> float:
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


def _union_bbox(bboxes) -> list[int]:
    items = list(bboxes)
    return [min(item[0] for item in items), min(item[1] for item in items), max(item[2] for item in items), max(item[3] for item in items)]


def _nearest_bbox_boundary_point(reference: list[float], bbox: list[int]) -> list[float]:
    x = min(max(float(reference[0]), float(bbox[0])), float(bbox[2]))
    y = min(max(float(reference[1]), float(bbox[1])), float(bbox[3]))
    candidates = [
        (abs(reference[0] - float(bbox[0])), [float(bbox[0]), y]),
        (abs(reference[0] - float(bbox[2])), [float(bbox[2]), y]),
        (abs(reference[1] - float(bbox[1])), [x, float(bbox[1])]),
        (abs(reference[1] - float(bbox[3])), [x, float(bbox[3])]),
    ]
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]
