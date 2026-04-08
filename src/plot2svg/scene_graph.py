"""Scene graph protocol for editable SVG assembly."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Iterable
from typing import Union

import cv2
import numpy as np

from .image_io import read_image, write_image

from .segment import ComponentProposal
from .svg_templates import append_template_role, extract_template_name

ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class SceneNode:
    """A component candidate in the intermediate editable representation."""

    id: str
    type: str
    bbox: list[int]
    z_index: int
    vector_mode: str
    confidence: float
    fill: str | None = None
    fill_opacity: float | None = None
    stroke: str | None = None
    stroke_width: float | None = None
    source_mask: str | None = None
    text_content: str | None = None
    group_id: str | None = None
    component_role: str | None = None
    children: list[str] = field(default_factory=list)
    shape_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SceneGroup:
    """Higher-level editable group built from low-level nodes."""

    id: str
    role: str
    bbox: list[int]
    child_ids: list[str]
    shape_type: str | None = None
    direction: str | None = None
    contains_group_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SceneRelation:
    """Explicit relationship between nodes or groups."""

    id: str
    relation_type: str
    source_ids: list[str]
    target_ids: list[str]
    backbone_id: str | None = None
    group_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class StrokePrimitive:
    """A traced stroke represented as an editable polyline."""

    id: str
    node_id: str
    points: list[list[float]]
    width: float
    arrow_head: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class NodeObject:
    """A detected graph node primitive."""

    id: str
    node_id: str
    center: list[float]
    radius: float
    fill: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RegionObject:
    """A mask-based vector region with optional holes."""

    id: str
    node_id: str
    outer_path: str
    holes: list[str]
    fill: str | None = None
    fill_opacity: float | None = None
    stroke: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class IconObject:
    """Compound-path icon object rendered with even-odd fill."""

    id: str
    node_id: str
    bbox: list[int]
    compound_path: str
    fill: str | None = None
    fill_rule: str = "evenodd"
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RasterObject:
    """Raster fallback object for complex icons that cannot be cleanly vectorized."""

    id: str
    node_id: str
    bbox: list[int]
    image_href: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class GraphEdge:
    """A reconstructed connection between two anchors."""

    id: str
    source_id: str | None
    target_id: str | None
    path: list[list[float]]
    backbone_id: str | None = None
    source_kind: str | None = None
    target_kind: str | None = None
    arrow_head: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SceneObject:
    """Higher-level semantic object assembled from nodes and groups."""

    id: str
    object_type: str
    bbox: list[int]
    node_ids: list[str]
    group_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SceneGraph:
    """Container for all editable component nodes."""

    width: int
    height: int
    nodes: list[SceneNode]
    groups: list[SceneGroup] = field(default_factory=list)
    relations: list[SceneRelation] = field(default_factory=list)
    objects: list[SceneObject] = field(default_factory=list)
    stroke_primitives: list[StrokePrimitive] = field(default_factory=list)
    node_objects: list[NodeObject] = field(default_factory=list)
    region_objects: list[RegionObject] = field(default_factory=list)
    icon_objects: list[IconObject] = field(default_factory=list)
    raster_objects: list[RasterObject] = field(default_factory=list)
    graph_edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "nodes": [node.to_dict() for node in self.nodes],
            "groups": [group.to_dict() for group in self.groups],
            "relations": [relation.to_dict() for relation in self.relations],
            "objects": [obj.to_dict() for obj in self.objects],
            "stroke_primitives": [primitive.to_dict() for primitive in self.stroke_primitives],
            "node_objects": [obj.to_dict() for obj in self.node_objects],
            "region_objects": [obj.to_dict() for obj in self.region_objects],
            "icon_objects": [obj.to_dict() for obj in self.icon_objects],
            "raster_objects": [obj.to_dict() for obj in self.raster_objects],
            "graph_edges": [edge.to_dict() for edge in self.graph_edges],
        }

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def build_scene_graph(width: int, height: int, proposals: list[ComponentProposal]) -> SceneGraph:
    """Build a scene graph from raw component proposals."""

    nodes: list[SceneNode] = [
        SceneNode(
            id="background-root",
            type="background",
            bbox=[0, 0, width, height],
            z_index=0,
            vector_mode="region_path",
            confidence=1.0,
            fill="#ffffff",
            stroke=None,
        )
    ]
    for index, proposal in enumerate(proposals):
        if proposal.proposal_type == "stroke":
            node_type = "stroke"
            vector_mode = "stroke_path"
            fill = None
        elif proposal.proposal_type == "text_like":
            node_type = "text"
            vector_mode = "text_path"
            fill = None
        else:
            node_type = "region"
            vector_mode = "region_path"
            fill = "#ffffff"
        nodes.append(
            SceneNode(
                id=proposal.component_id,
                type=node_type,
                bbox=proposal.bbox,
                z_index=index + 1,
                vector_mode=vector_mode,
                confidence=proposal.confidence,
                fill=fill,
                fill_opacity=1.0 if fill else None,
                stroke="#000000",
                source_mask=proposal.mask_path,
                shape_hint=proposal.shape_hint,
            )
        )
    return SceneGraph(width=width, height=height, nodes=nodes)


def promote_component_groups(scene_graph: SceneGraph) -> SceneGraph:
    """Promote low-level nodes into higher-level editable component groups."""

    groups: list[SceneGroup] = []
    assigned_ids: set[str] = set()
    updated_nodes = {node.id: node for node in scene_graph.nodes}
    title_node_ids = {
        node_id
        for obj in scene_graph.objects
        if obj.object_type == "title"
        for node_id in obj.node_ids
    }
    blocked_region_ids = {
        node_id
        for obj in scene_graph.objects
        if obj.object_type in {"network_container", "cluster_region"}
        for node_id in obj.node_ids
    }

    text_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == "text" and (node.text_content or "").strip()
        and node.id not in title_node_ids
    ]
    title_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == "text" and (node.text_content or "").strip()
        and node.id in title_node_ids
    ]
    region_nodes = [node for node in scene_graph.nodes if node.type == "region"]
    stroke_nodes = [node for node in scene_graph.nodes if node.type == "stroke"]

    for text_node in text_nodes:
        region = _find_anchor_region(text_node, region_nodes, blocked_region_ids)
        if region is not None:
            child_nodes = [region, text_node]
            nearby_strokes = _find_nearby_strokes(region, stroke_nodes, limit=4)
            child_nodes.extend(nearby_strokes)
            child_ids = _unique_node_ids(child_nodes)
            group_id = f"component-{region.id}"
            bbox = _union_bboxes(node.bbox for node in child_nodes)
            groups.append(SceneGroup(id=group_id, role="labeled_region", bbox=bbox, child_ids=child_ids))
            for child in child_nodes:
                updated_nodes[child.id] = _with_group_metadata(
                    child,
                    group_id=group_id,
                    component_role=_component_role_for_child(child),
                )
                assigned_ids.add(child.id)
            continue

        nearby_details = _find_nearby_detail_nodes(text_node, region_nodes, stroke_nodes, assigned_ids)
        if nearby_details:
            child_nodes = [text_node, *nearby_details]
            child_ids = _unique_node_ids(child_nodes)
            group_id = f"component-{text_node.id}"
            bbox = _union_bboxes(node.bbox for node in child_nodes)
            groups.append(SceneGroup(id=group_id, role="labeled_component", bbox=bbox, child_ids=child_ids))
            for child in child_nodes:
                updated_nodes[child.id] = _with_group_metadata(
                    child,
                    group_id=group_id,
                    component_role=_component_role_for_child(child),
                )
                assigned_ids.add(child.id)
            continue

        if text_node.id in assigned_ids:
            continue
        group_id = f"component-{text_node.id}"
        groups.append(SceneGroup(id=group_id, role="text_label", bbox=text_node.bbox[:], child_ids=[text_node.id]))
        updated_nodes[text_node.id] = _with_group_metadata(
            text_node,
            group_id=group_id,
            component_role="label_text",
        )
        assigned_ids.add(text_node.id)

    for title_node in title_nodes:
        group_id = f"component-{title_node.id}"
        groups.append(SceneGroup(id=group_id, role="text_label", bbox=title_node.bbox[:], child_ids=[title_node.id]))
        updated_nodes[title_node.id] = _with_group_metadata(
            title_node,
            group_id=group_id,
            component_role="label_text",
        )
        assigned_ids.add(title_node.id)

    for stroke_node in stroke_nodes:
        if stroke_node.id in assigned_ids:
            continue
        if not _looks_like_connector(stroke_node):
            continue
        group_id = f"component-{stroke_node.id}"
        groups.append(SceneGroup(id=group_id, role="connector", bbox=stroke_node.bbox[:], child_ids=[stroke_node.id]))
        updated_nodes[stroke_node.id] = _with_group_metadata(
            stroke_node,
            group_id=group_id,
            component_role="connector_path",
        )
        assigned_ids.add(stroke_node.id)

    ordered_nodes = [updated_nodes[node.id] for node in scene_graph.nodes]
    updated_objects = _attach_group_ids_to_objects(scene_graph.objects, groups)
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=ordered_nodes,
        groups=groups,
        relations=scene_graph.relations[:],
        objects=updated_objects,
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _find_anchor_region(
    text_node: SceneNode,
    region_nodes: list[SceneNode],
    blocked_region_ids: set[str] | None = None,
) -> SceneNode | None:
    text_area = _bbox_area(text_node.bbox)
    candidates: list[tuple[int, int, SceneNode]] = []
    blocked_region_ids = blocked_region_ids or set()
    for region_node in region_nodes:
        if region_node.id in blocked_region_ids:
            continue
        region_area = _bbox_area(region_node.bbox)
        if region_area <= text_area:
            continue
        if region_area > text_area * 120:
            continue
        if _contains_bbox(region_node.bbox, text_node.bbox, margin=18) or _overlap_ratio(region_node.bbox, text_node.bbox) >= 0.55:
            candidates.append((region_area, abs(region_node.z_index - text_node.z_index), region_node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def build_object_instances(scene_graph: SceneGraph) -> SceneGraph:
    """Build a minimal semantic object layer before group promotion."""

    node_map = {node.id: node for node in scene_graph.nodes}
    text_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == "text" and (node.text_content or "").strip()
    ]
    region_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == "region" and node.id != "background-root"
    ]

    objects: list[SceneObject] = []
    consumed_text_ids: set[str] = set()
    cluster_blocked_text_ids: set[str] = set()
    consumed_region_ids: set[str] = set()
    canvas_area = max(scene_graph.width * scene_graph.height, 1)

    for text_node in text_nodes:
        if _looks_like_title_text(text_node, scene_graph.height):
            objects.append(
                SceneObject(
                    id=f"object-{text_node.id}",
                    object_type="title",
                    bbox=text_node.bbox[:],
                    node_ids=[text_node.id],
                    metadata={"title_text": text_node.text_content or ""},
                )
            )
            consumed_text_ids.add(text_node.id)

    for region_node in region_nodes:
        contained_texts = [
            text_node
            for text_node in text_nodes
            if text_node.id not in consumed_text_ids
            and _contains_bbox(region_node.bbox, text_node.bbox, margin=18)
        ]
        if not contained_texts:
            continue
        if not _looks_like_label_box_region(region_node, contained_texts, scene_graph):
            continue
        node_ids = [region_node.id, *[text_node.id for text_node in contained_texts]]
        objects.append(
            SceneObject(
                id=f"object-{region_node.id}",
                object_type="label_box",
                bbox=_union_bboxes(node_map[node_id].bbox for node_id in node_ids),
                node_ids=node_ids,
                metadata={"text_count": len(contained_texts), "box_like": True},
            )
        )
        consumed_region_ids.add(region_node.id)
        consumed_text_ids.update(text_node.id for text_node in contained_texts)
        cluster_blocked_text_ids.update(text_node.id for text_node in contained_texts)

    remaining_text_nodes = [
        text_node
        for text_node in text_nodes
        if text_node.id not in cluster_blocked_text_ids
    ]
    for cluster_nodes in _find_text_cluster_candidates(remaining_text_nodes, scene_graph):
        node_ids = [node.id for node in cluster_nodes]
        objects.append(
            SceneObject(
                id=f"object-text-cluster-{node_ids[0]}",
                object_type="text_cluster",
                bbox=_union_bboxes(node.bbox for node in cluster_nodes),
                node_ids=node_ids,
                metadata={
                    "text_count": len(node_ids),
                    "layout": "vertical_stack",
                },
            )
        )
        consumed_text_ids.update(node_ids)

    for region_node in region_nodes:
        if region_node.id in consumed_region_ids:
            continue
        contained_nodes = _contained_object_candidate_nodes(region_node, scene_graph.nodes)
        node_shape_count = sum(1 for node in contained_nodes if _is_node_like_shape_hint(node.shape_hint))
        circle_count = sum(1 for node in contained_nodes if node.shape_hint == "circle")
        stroke_count = sum(1 for node in contained_nodes if node.type == "stroke")
        if _looks_like_network_container(region_node, contained_nodes, canvas_area):
            objects.append(
                SceneObject(
                    id=f"object-{region_node.id}",
                    object_type="network_container",
                    bbox=region_node.bbox[:],
                    node_ids=[region_node.id, *[node.id for node in contained_nodes]],
                    metadata={
                        "contained_count": len(contained_nodes),
                        "circle_count": circle_count,
                        "node_shape_count": node_shape_count,
                        "stroke_count": stroke_count,
                        "box_like": False,
                    },
                )
            )
            consumed_region_ids.add(region_node.id)
            continue
        if _looks_like_cluster_region(region_node, contained_nodes, canvas_area):
            objects.append(
                SceneObject(
                    id=f"object-{region_node.id}",
                    object_type="cluster_region",
                    bbox=region_node.bbox[:],
                    node_ids=[region_node.id, *[node.id for node in contained_nodes]],
                    metadata={
                        "contained_count": len(contained_nodes),
                        "circle_count": circle_count,
                        "node_shape_count": node_shape_count,
                        "box_like": False,
                    },
                )
            )

    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=scene_graph.nodes[:],
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=_dedupe_objects(objects),
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _looks_like_title_text(text_node: SceneNode, canvas_height: int) -> bool:
    width = max(text_node.bbox[2] - text_node.bbox[0], 1)
    height = max(text_node.bbox[3] - text_node.bbox[1], 1)
    return text_node.bbox[1] <= max(int(canvas_height * 0.12), 64) and width >= 50 and height <= 48


def _looks_like_label_box_region(
    region_node: SceneNode,
    contained_texts: list[SceneNode],
    scene_graph: SceneGraph,
) -> bool:
    width = max(region_node.bbox[2] - region_node.bbox[0], 1)
    height = max(region_node.bbox[3] - region_node.bbox[1], 1)
    area = _bbox_area(region_node.bbox)
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    if width < 40 or height < 24:
        return False
    if area > canvas_area * 0.08:
        return False
    contained_nodes = _contained_object_candidate_nodes(region_node, scene_graph.nodes)
    node_shape_count = sum(1 for node in contained_nodes if _is_node_like_shape_hint(node.shape_hint))
    stroke_count = sum(1 for node in contained_nodes if node.type == "stroke")
    return node_shape_count <= 1 and stroke_count <= 3 and len(contained_texts) >= 1


def _find_text_cluster_candidates(
    text_nodes: list[SceneNode],
    scene_graph: SceneGraph,
) -> list[list[SceneNode]]:
    if len(text_nodes) < 3:
        return []

    ordered_nodes = sorted(text_nodes, key=lambda node: (node.bbox[1], node.bbox[0], node.id))
    node_map = {node.id: node for node in ordered_nodes}
    adjacency = {node.id: set() for node in ordered_nodes}
    for index, node in enumerate(ordered_nodes):
        for other in ordered_nodes[index + 1:]:
            if _text_nodes_share_cluster(node, other):
                adjacency[node.id].add(other.id)
                adjacency[other.id].add(node.id)

    clusters: list[list[SceneNode]] = []
    visited: set[str] = set()
    for node in ordered_nodes:
        if node.id in visited:
            continue
        stack = [node.id]
        component_ids: list[str] = []
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            component_ids.append(current_id)
            stack.extend(neighbor_id for neighbor_id in adjacency[current_id] if neighbor_id not in visited)
        cluster_nodes = sorted(
            (node_map[node_id] for node_id in component_ids),
            key=lambda item: (item.bbox[1], item.bbox[0], item.id),
        )
        clusters.extend(_extract_text_cluster_runs(cluster_nodes, scene_graph))
    return clusters


def _extract_text_cluster_runs(
    cluster_nodes: list[SceneNode],
    scene_graph: SceneGraph,
) -> list[list[SceneNode]]:
    if _is_valid_text_cluster(cluster_nodes, scene_graph):
        return [cluster_nodes]

    runs: list[list[SceneNode]] = []
    start_index = 0
    while start_index < len(cluster_nodes):
        best_run: list[SceneNode] | None = None
        max_end = min(len(cluster_nodes), start_index + 6)
        for end_index in range(max_end, start_index + 2, -1):
            candidate = cluster_nodes[start_index:end_index]
            if _is_valid_text_cluster(candidate, scene_graph):
                best_run = candidate
                break
        if best_run is not None:
            runs.append(best_run)
            start_index += len(best_run)
            continue
        start_index += 1
    return runs


def _text_nodes_share_cluster(left: SceneNode, right: SceneNode) -> bool:
    left_width = max(left.bbox[2] - left.bbox[0], 1)
    right_width = max(right.bbox[2] - right.bbox[0], 1)
    left_height = max(left.bbox[3] - left.bbox[1], 1)
    right_height = max(right.bbox[3] - right.bbox[1], 1)
    width_ratio = max(left_width / right_width, right_width / left_width)
    if width_ratio > 2.5:
        return False

    horizontal_overlap = _axis_overlap(left.bbox[0], left.bbox[2], right.bbox[0], right.bbox[2])
    min_width = max(min(left_width, right_width), 1)
    overlap_ratio = horizontal_overlap / float(min_width)
    center_distance = abs(_bbox_center_x(left.bbox) - _bbox_center_x(right.bbox))
    left_edge_delta = abs(left.bbox[0] - right.bbox[0])
    right_edge_delta = abs(left.bbox[2] - right.bbox[2])
    aligned = overlap_ratio >= 0.55 or center_distance <= 42.0 or left_edge_delta <= 36 or right_edge_delta <= 42
    if not aligned:
        return False

    vertical_gap = _axis_gap(left.bbox[1], left.bbox[3], right.bbox[1], right.bbox[3])
    max_gap = max(int(max(left_height, right_height) * 6), 260)
    return vertical_gap <= max_gap


def _is_valid_text_cluster(cluster_nodes: list[SceneNode], scene_graph: SceneGraph) -> bool:
    if len(cluster_nodes) < 3:
        return False
    if len(cluster_nodes) > 6:
        return False

    bbox = _union_bboxes(node.bbox for node in cluster_nodes)
    cluster_width = max(bbox[2] - bbox[0], 1)
    cluster_height = max(bbox[3] - bbox[1], 1)
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    if cluster_width > scene_graph.width * 0.45:
        return False
    if cluster_height > scene_graph.height * 0.82:
        return False
    if _bbox_area(bbox) > canvas_area * 0.18:
        return False

    widths = [max(node.bbox[2] - node.bbox[0], 1) for node in cluster_nodes]
    heights = [max(node.bbox[3] - node.bbox[1], 1) for node in cluster_nodes]
    if max(widths) / max(min(widths), 1) > 2.5:
        return False
    if max(heights) / max(min(heights), 1) > 1.8:
        return False
    if sum(widths) / float(len(widths)) < 60.0:
        return False

    sorted_nodes = sorted(cluster_nodes, key=lambda node: (node.bbox[1], node.bbox[0], node.id))
    left_span = max(node.bbox[0] for node in sorted_nodes) - min(node.bbox[0] for node in sorted_nodes)
    right_span = max(node.bbox[2] for node in sorted_nodes) - min(node.bbox[2] for node in sorted_nodes)
    center_span = max(_bbox_center_x(node.bbox) for node in sorted_nodes) - min(_bbox_center_x(node.bbox) for node in sorted_nodes)
    if left_span > 42 or right_span > 52 or center_span > 48.0:
        return False

    gaps = [
        _axis_gap(left.bbox[1], left.bbox[3], right.bbox[1], right.bbox[3])
        for left, right in zip(sorted_nodes, sorted_nodes[1:])
    ]
    return max(gaps, default=0) <= 260


def _bbox_center_x(bbox: list[int]) -> float:
    return (bbox[0] + bbox[2]) / 2.0


def _axis_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(min(end_a, end_b) - max(start_a, start_b), 0)


def _axis_gap(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(start_a - end_b, start_b - end_a, 0)


def _contained_object_candidate_nodes(region_node: SceneNode, nodes: list[SceneNode]) -> list[SceneNode]:
    contained: list[SceneNode] = []
    for node in nodes:
        if node.id == region_node.id or node.id == "background-root":
            continue
        if _contains_bbox(region_node.bbox, node.bbox, margin=12):
            contained.append(node)
    return contained


def _looks_like_network_container(
    region_node: SceneNode,
    contained_nodes: list[SceneNode],
    canvas_area: int,
) -> bool:
    area = _bbox_area(region_node.bbox)
    width = max(region_node.bbox[2] - region_node.bbox[0], 1)
    height = max(region_node.bbox[3] - region_node.bbox[1], 1)
    node_shape_count = sum(1 for node in contained_nodes if _is_node_like_shape_hint(node.shape_hint))
    stroke_count = sum(1 for node in contained_nodes if node.type == "stroke")
    text_count = sum(1 for node in contained_nodes if node.type == "text")
    if area < canvas_area * 0.05:
        return False
    if area < canvas_area * 0.08 and node_shape_count < 4:
        return False
    if min(width, height) < 120:
        return False
    return len(contained_nodes) >= 6 or node_shape_count >= 3 or stroke_count >= 2 or text_count >= 2


def _looks_like_cluster_region(
    region_node: SceneNode,
    contained_nodes: list[SceneNode],
    canvas_area: int,
) -> bool:
    area = _bbox_area(region_node.bbox)
    node_shape_count = sum(1 for node in contained_nodes if _is_node_like_shape_hint(node.shape_hint))
    return area >= canvas_area * 0.025 and len(contained_nodes) >= 3 and node_shape_count >= 2


def _dedupe_objects(objects: list[SceneObject]) -> list[SceneObject]:
    seen: set[str] = set()
    deduped: list[SceneObject] = []
    for obj in objects:
        if obj.id in seen:
            continue
        seen.add(obj.id)
        deduped.append(obj)
    return deduped


def _attach_group_ids_to_objects(objects: list[SceneObject], groups: list[SceneGroup]) -> list[SceneObject]:
    updated: list[SceneObject] = []
    for obj in objects:
        group_ids = [
            group.id
            for group in groups
            if set(group.child_ids) & set(obj.node_ids)
        ]
        updated.append(
            SceneObject(
                id=obj.id,
                object_type=obj.object_type,
                bbox=obj.bbox[:],
                node_ids=obj.node_ids[:],
                group_ids=group_ids,
                metadata=obj.metadata.copy(),
            )
        )
    return updated


def _find_nearby_strokes(region_node: SceneNode, stroke_nodes: list[SceneNode], limit: int) -> list[SceneNode]:
    candidates: list[tuple[int, SceneNode]] = []
    for stroke_node in stroke_nodes:
        if _bbox_area(stroke_node.bbox) > _bbox_area(region_node.bbox) * 0.9:
            continue
        if _overlap_ratio(region_node.bbox, stroke_node.bbox) > 0.0 or _bbox_gap(region_node.bbox, stroke_node.bbox) <= 14:
            candidates.append((_bbox_gap(region_node.bbox, stroke_node.bbox), stroke_node))
    candidates.sort(key=lambda item: item[0])
    return [node for _, node in candidates[:limit]]


def _find_nearby_detail_nodes(
    text_node: SceneNode,
    region_nodes: list[SceneNode],
    stroke_nodes: list[SceneNode],
    assigned_ids: set[str],
) -> list[SceneNode]:
    text_area = _bbox_area(text_node.bbox)
    text_height = max(text_node.bbox[3] - text_node.bbox[1], 1)
    max_gap = max(18, int(text_height * 1.25))
    candidates: list[tuple[int, int, SceneNode]] = []
    for node in [*region_nodes, *stroke_nodes]:
        if node.id in assigned_ids:
            continue
        if node.id == text_node.id:
            continue
        node_area = _bbox_area(node.bbox)
        if node_area > text_area * 80:
            continue
        gap = _bbox_gap(text_node.bbox, node.bbox)
        if gap > max_gap and _overlap_ratio(text_node.bbox, node.bbox) == 0.0:
            continue
        overlap = _overlap_ratio(text_node.bbox, node.bbox)
        if node.type == "stroke" and not _looks_like_connector(node) and gap <= max_gap:
            candidates.append((gap, node.z_index, node))
            continue
        if node.type == "region" and (overlap > 0.0 or gap <= max_gap):
            candidates.append((gap, node.z_index, node))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [node for _, _, node in candidates[:4]]


def _component_role_for_child(node: SceneNode) -> str:
    if node.type == "region":
        return "container_shape"
    if node.type == "stroke":
        return "connector_path" if _looks_like_connector(node) else "container_detail"
    if node.type == "text":
        return "label_text"
    return node.type


def _with_group_metadata(node: SceneNode, *, group_id: str, component_role: str) -> SceneNode:
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


def _is_node_like_shape_hint(shape_hint: str | None) -> bool:
    return shape_hint in {"circle", "triangle", "pentagon"}


def _bbox_area(bbox: list[int]) -> int:
    return max(bbox[2] - bbox[0], 1) * max(bbox[3] - bbox[1], 1)


def _contains_bbox(outer: list[int], inner: list[int], margin: int) -> bool:
    return (
        outer[0] - margin <= inner[0]
        and outer[1] - margin <= inner[1]
        and outer[2] + margin >= inner[2]
        and outer[3] + margin >= inner[3]
    )


def _overlap_ratio(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    return intersection / max(min(_bbox_area(left), _bbox_area(right)), 1)


def _bbox_gap(left: list[int], right: list[int]) -> int:
    horizontal_gap = max(left[0] - right[2], right[0] - left[2], 0)
    vertical_gap = max(left[1] - right[3], right[1] - left[3], 0)
    return max(horizontal_gap, vertical_gap)


def _union_bboxes(bboxes: Iterable[list[int]]) -> list[int]:
    items = list(bboxes)
    return [
        min(bbox[0] for bbox in items),
        min(bbox[1] for bbox in items),
        max(bbox[2] for bbox in items),
        max(bbox[3] for bbox in items),
    ]


def _unique_node_ids(nodes: Iterable[SceneNode]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        ordered.append(node.id)
    return ordered


def _looks_like_connector(node: SceneNode) -> bool:
    width = max(node.bbox[2] - node.bbox[0], 1)
    height = max(node.bbox[3] - node.bbox[1], 1)
    area = width * height
    longest_side = max(width, height)
    shortest_side = min(width, height)
    aspect_ratio = max(width / height, height / width)
    if aspect_ratio >= 4.0 and longest_side >= 36:
        return True
    if aspect_ratio >= 2.0 and longest_side >= 24 and shortest_side <= 48 and area <= 3600:
        return True
    if longest_side >= 48 and shortest_side <= 48 and area <= 3000:
        return True
    return False


def enrich_region_styles(
    image_input: ImageInput,
    scene_graph: SceneGraph,
    coordinate_scale: float = 1.0,
) -> SceneGraph:
    """Sample fill/stroke styles from the source raster for region nodes."""

    image = _load_color_image(image_input)
    nodes: list[SceneNode] = []
    for node in scene_graph.nodes:
        if node.type != "region" or node.id == "background-root":
            nodes.append(node)
            continue
        fill, fill_opacity, stroke = _sample_region_style(image, node.bbox, coordinate_scale, node.shape_hint)
        nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=node.z_index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=fill,
                fill_opacity=fill_opacity,
                stroke=stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=node.component_role,
                children=node.children[:],
                shape_hint=node.shape_hint,
            )
        )
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _sample_region_style(
    image: np.ndarray,
    bbox: list[int],
    coordinate_scale: float,
    shape_hint: str | None,
) -> tuple[str | None, float | None, str | None]:
    crop = _extract_scaled_crop(image, bbox, coordinate_scale)
    if crop.size == 0:
        return "#ffffff", 1.0, "#000000"

    center_crop = _center_crop(crop)
    center_mask = _non_white_mask(center_crop)
    full_mask = _non_white_mask(crop)
    fill_ratio = float(full_mask.mean()) if full_mask.size else 0.0

    fill_color = _dominant_color(center_crop, center_mask)
    if fill_color is None:
        fill_color = _dominant_color(crop, full_mask)

    stroke_color = _dominant_color(_border_crop(crop), _non_white_mask(_border_crop(crop)))
    if stroke_color is None:
        stroke_color = "#000000"

    if fill_color is None:
        return "#ffffff", 1.0, stroke_color

    brightness = _color_brightness(fill_color)
    if shape_hint is None and brightness < 72 and fill_ratio < 0.45:
        return "none", None, stroke_color
    if fill_ratio < 0.08 and shape_hint is None:
        return "none", None, stroke_color

    fill_opacity = _estimate_fill_opacity(fill_color, fill_ratio, bbox, shape_hint)
    return fill_color, fill_opacity, stroke_color


def _estimate_fill_opacity(
    fill_color: str,
    fill_ratio: float,
    bbox: list[int],
    shape_hint: str | None,
) -> float:
    if shape_hint == "circle":
        return 0.95
    width = max(bbox[2] - bbox[0], 1)
    height = max(bbox[3] - bbox[1], 1)
    brightness = _color_brightness(fill_color)
    if width >= 140 and height >= 120 and brightness >= 165:
        return 0.4
    if brightness >= 185 and fill_ratio >= 0.12:
        return 0.55
    return 0.95


def _color_brightness(color: str) -> float:
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return (r + g + b) / 3.0


def _dominant_color(image: np.ndarray, mask: np.ndarray) -> str | None:
    if image.size == 0 or mask.size == 0 or not np.any(mask):
        return None
    pixels = image[mask].reshape(-1, 3)
    if len(pixels) == 0:
        return None
    quantized = ((pixels.astype(np.int32) + 8) // 16) * 16
    unique, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = unique[int(np.argmax(counts))]
    b, g, r = [int(np.clip(channel, 0, 255)) for channel in dominant]
    return f"#{r:02x}{g:02x}{b:02x}"


def _non_white_mask(image: np.ndarray) -> np.ndarray:
    if image.size == 0:
        return np.zeros((0, 0), dtype=bool)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    saturation = hsv[:, :, 1]
    return (gray < 242) | (saturation > 18)


def _center_crop(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    x1 = int(width * 0.2)
    y1 = int(height * 0.2)
    x2 = max(int(width * 0.8), x1 + 1)
    y2 = max(int(height * 0.8), y1 + 1)
    return image[y1:y2, x1:x2]


def _border_crop(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    border = max(min(height, width) // 8, 2)
    mask = np.zeros((height, width), dtype=bool)
    mask[:border, :] = True
    mask[-border:, :] = True
    mask[:, :border] = True
    mask[:, -border:] = True
    flat = image[mask]
    if flat.size == 0:
        return image
    return flat.reshape(-1, 1, 3)


def _extract_scaled_crop(image: np.ndarray, bbox: list[int], coordinate_scale: float) -> np.ndarray:
    source_bbox = _scale_bbox(bbox, coordinate_scale, image.shape[1], image.shape[0])
    x1, y1, x2, y2 = source_bbox
    crop = image[y1:y2, x1:x2]
    if crop.size == 0 or coordinate_scale == 1.0:
        return crop
    target_width = max(bbox[2] - bbox[0], 1)
    target_height = max(bbox[3] - bbox[1], 1)
    return cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_CUBIC)


def _scale_bbox(
    bbox: list[int],
    coordinate_scale: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    scaled = [int(round(coord * coordinate_scale)) for coord in bbox]
    return _clamp_bbox(scaled, width, height)


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image
