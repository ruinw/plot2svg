"""Scene graph protocol for editable SVG assembly."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Iterable

from .segment import ComponentProposal


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
    stroke: str | None = None
    stroke_width: float | None = None
    source_mask: str | None = None
    text_content: str | None = None
    group_id: str | None = None
    component_role: str | None = None
    children: list[str] = field(default_factory=list)

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
class SceneGraph:
    """Container for all editable component nodes."""

    width: int
    height: int
    nodes: list[SceneNode]
    groups: list[SceneGroup] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "nodes": [node.to_dict() for node in self.nodes],
            "groups": [group.to_dict() for group in self.groups],
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
                stroke="#000000",
                source_mask=proposal.mask_path,
            )
        )
    return SceneGraph(width=width, height=height, nodes=nodes)


def promote_component_groups(scene_graph: SceneGraph) -> SceneGraph:
    """Promote low-level nodes into higher-level editable component groups."""

    groups: list[SceneGroup] = []
    assigned_ids: set[str] = set()
    updated_nodes = {node.id: node for node in scene_graph.nodes}

    text_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == "text" and (node.text_content or "").strip()
    ]
    region_nodes = [node for node in scene_graph.nodes if node.type == "region"]
    stroke_nodes = [node for node in scene_graph.nodes if node.type == "stroke"]

    for text_node in text_nodes:
        region = _find_anchor_region(text_node, region_nodes)
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
    return SceneGraph(width=scene_graph.width, height=scene_graph.height, nodes=ordered_nodes, groups=groups)


def _find_anchor_region(text_node: SceneNode, region_nodes: list[SceneNode]) -> SceneNode | None:
    text_area = _bbox_area(text_node.bbox)
    candidates: list[tuple[int, int, SceneNode]] = []
    for region_node in region_nodes:
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
    return SceneNode(
        id=node.id,
        type=node.type,
        bbox=node.bbox[:],
        z_index=node.z_index,
        vector_mode=node.vector_mode,
        confidence=node.confidence,
        fill=node.fill,
        stroke=node.stroke,
        stroke_width=node.stroke_width,
        source_mask=node.source_mask,
        text_content=node.text_content,
        group_id=group_id,
        component_role=component_role,
        children=node.children[:],
    )


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
    aspect_ratio = max(width / height, height / width)
    return aspect_ratio >= 4.0 and max(width, height) >= 36
