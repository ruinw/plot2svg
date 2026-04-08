"""Grouped SVG export helpers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import shutil

from .object_svg_exporter import export_object_scene_graph
from .scene_graph import SceneGraph, SceneGroup, SceneNode, SceneObject, SceneRelation
from .vectorize_region import RegionVectorResult
from .vectorize_stroke import StrokeVectorResult

_STANDARD_ARROW_DEFS = '''
<defs>
  <marker id='standard-arrow' markerWidth='10' markerHeight='7' refX='9' refY='3.5' orient='auto'>
    <polygon points='0 0, 10 3.5, 0 7' fill='#555555' />
  </marker>
</defs>
'''

_EMPTY_PREVIEW_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc```\xf8"
    b"\x0f\x00\x01\x04\x01\x00_\xd4\xa2\xf5\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass(slots=True)
class SvgExportResult:
    """Paths emitted by SVG export."""

    svg_path: Path
    preview_path: Path
    group_count: int


def build_svg_group_id(component_id: str) -> str:
    """Keep group ids stable across exports."""

    return component_id


def export_svg(
    scene_graph: SceneGraph,
    region_results: list[RegionVectorResult],
    stroke_results: list[StrokeVectorResult],
    output_dir: Path,
    preview_source_path: Path | None = None,
) -> SvgExportResult:
    """Assemble a grouped SVG from region and stroke fragments."""

    output_dir.mkdir(parents=True, exist_ok=True)
    region_map = {result.component_id: result for result in region_results}
    stroke_map = {result.component_id: result for result in stroke_results}
    relation_map = {
        relation.group_id: relation
        for relation in scene_graph.relations
        if relation.group_id is not None
    }
    object_map = {
        group_id: obj
        for obj in scene_graph.objects
        for group_id in obj.group_ids
    }

    grouped_node_ids = {child_id for group in scene_graph.groups for child_id in group.child_ids}
    groups: list[str] = []

    if scene_graph.region_objects or scene_graph.icon_objects or scene_graph.node_objects or scene_graph.raster_objects or scene_graph.graph_edges:
        groups.extend(
            export_object_scene_graph(
                scene_graph,
                fallback_region_map=region_map,
                fallback_stroke_map=stroke_map,
            )
        )
        for group in scene_graph.groups:
            relation = relation_map.get(group.id)
            if group.shape_type != "fan" and not (relation is not None and relation.relation_type == "fan"):
                continue
            child_fragments = _render_group_fragments(scene_graph, group, region_map, stroke_map, relation)
            if not child_fragments:
                continue
            shape_attrs = _shape_attrs(group, relation, object_map.get(group.id))
            groups.append(
                "\n".join(
                    [
                        f"  <g id='{build_svg_group_id(group.id)}' data-node-type='group' data-component-role='{group.role}'{shape_attrs}>",
                        *[f"    {fragment}" for fragment in child_fragments],
                        "  </g>",
                    ]
                )
            )
    else:
        for group in scene_graph.groups:
            child_fragments = _render_group_fragments(scene_graph, group, region_map, stroke_map, relation_map.get(group.id))
            if not child_fragments:
                continue
            shape_attrs = _shape_attrs(group, relation_map.get(group.id), object_map.get(group.id))
            groups.append(
                "\n".join(
                    [
                        f"  <g id='{build_svg_group_id(group.id)}' data-node-type='group' data-component-role='{group.role}'{shape_attrs}>",
                        *[f"    {fragment}" for fragment in child_fragments],
                        "  </g>",
                    ]
                )
            )

        for node in sorted(scene_graph.nodes, key=lambda item: item.z_index):
            if node.id in grouped_node_ids:
                continue
            fragment = _render_node_fragment(node, region_map, stroke_map)
            if fragment is None:
                continue
            groups.append(fragment)

    groups = [
        fragment
        for fragment in groups
        if not _should_drop_pure_black_region_fragment(fragment)
    ]

    svg_content = "\n".join(
        [
            f"<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='{scene_graph.width}' height='{scene_graph.height}' viewBox='0 0 {scene_graph.width} {scene_graph.height}'>",
            _STANDARD_ARROW_DEFS,
            *groups,
            "</svg>",
        ]
    )
    svg_path = output_dir / "final.svg"
    svg_path.write_text(svg_content, encoding="utf-8")

    preview_path = output_dir / "preview.png"
    if preview_source_path is not None and Path(preview_source_path).exists():
        shutil.copyfile(preview_source_path, preview_path)
    else:
        preview_path.write_bytes(_EMPTY_PREVIEW_PNG)

    return SvgExportResult(svg_path=svg_path, preview_path=preview_path, group_count=len(groups))


def _resolve_group_nodes(scene_graph: SceneGraph, child_ids: list[str]):
    node_map = {node.id: node for node in scene_graph.nodes}
    return [node_map[child_id] for child_id in child_ids if child_id in node_map]


def _render_group_fragments(
    scene_graph: SceneGraph,
    group: SceneGroup,
    region_map: dict[str, RegionVectorResult],
    stroke_map: dict[str, StrokeVectorResult],
    relation: SceneRelation | None,
) -> list[str]:
    nodes = sorted(_resolve_group_nodes(scene_graph, group.child_ids), key=lambda item: item.z_index)
    if relation is not None and relation.relation_type == "connector":
        connector_fragments = _render_connector_group(scene_graph, group, relation)
        if connector_fragments:
            return connector_fragments
    if group.shape_type == "fan":
        return _render_fan_group(nodes, group, relation, region_map, stroke_map)

    child_fragments: list[str] = []
    for node in nodes:
        fragment = _render_node_fragment(node, region_map, stroke_map)
        if fragment is None:
            continue
        child_fragments.append(fragment)
    return child_fragments


def _render_fan_group(
    nodes: list[SceneNode],
    group: SceneGroup,
    relation: SceneRelation | None,
    region_map: dict[str, RegionVectorResult],
    stroke_map: dict[str, StrokeVectorResult],
) -> list[str]:
    source_nodes = [
        node for node in nodes
        if node.type == "region" and node.shape_hint == "circle"
    ]
    target_node = next(
        (
            node for node in nodes
            if node.type == "region" and node.shape_hint != "circle"
        ),
        None,
    )
    stroke_node = next((node for node in nodes if node.type == "stroke"), None)

    fragments: list[str] = []
    fan_path = _render_fan_backbone(group, relation, source_nodes, target_node, stroke_node)
    if fan_path is not None:
        fragments.append(fan_path)

    for node in nodes:
        if node.type == "stroke":
            continue
        fragment = _render_node_fragment(node, region_map, stroke_map)
        if fragment is None:
            continue
        fragments.append(fragment)
    return fragments


def _render_connector_group(
    scene_graph: SceneGraph,
    group: SceneGroup,
    relation: SceneRelation,
) -> list[str]:
    node_map = {node.id: node for node in scene_graph.nodes}
    source_node = next((node_map[node_id] for node_id in relation.source_ids if node_id in node_map), None)
    target_node = next((node_map[node_id] for node_id in relation.target_ids if node_id in node_map), None)
    if source_node is None or target_node is None:
        return []

    source_center = _node_center(source_node)
    target_center = _node_center(target_node)
    start_x, start_y = _bbox_anchor_point(source_node.bbox, target_center)
    end_x, end_y = _bbox_anchor_point(target_node.bbox, source_center)
    relation_attrs = _relation_path_attrs(relation)
    marker_attr = " marker-end='url(#standard-arrow)'" if group.shape_type == "arrow" else ""

    line = (
        f"<line id='{group.id}-connector' x1='{start_x:.1f}' y1='{start_y:.1f}' x2='{end_x:.1f}' y2='{end_y:.1f}' "
        f"fill='none' stroke='#555555' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'{marker_attr}{relation_attrs} />"
    )
    return [line]


def _render_fan_backbone(
    group: SceneGroup,
    relation: SceneRelation | None,
    source_nodes: list[SceneNode],
    target_node: SceneNode | None,
    stroke_node: SceneNode | None,
) -> str | None:
    if len(source_nodes) < 2:
        return None
    source_nodes = sorted(source_nodes, key=lambda item: _node_center(item)[1])
    if stroke_node is not None:
        hub_x = stroke_node.bbox[2] - 12
    else:
        hub_x = max(_node_center(node)[0] for node in source_nodes) + 48
    hub_y = sum(_node_center(node)[1] for node in source_nodes) / len(source_nodes)

    commands: list[str] = []
    for node in source_nodes:
        cx, cy = _node_center(node)
        commands.append(f"M {cx:.1f} {cy:.1f} L {hub_x:.1f} {hub_y:.1f}")

    if target_node is not None:
        target_y = min(max(hub_y, float(target_node.bbox[1] + 4)), float(target_node.bbox[3] - 4))
        commands.append(f"M {hub_x:.1f} {hub_y:.1f} L {float(target_node.bbox[0]):.1f} {target_y:.1f}")

    return (
        f"<path id='{group.id}-backbone' d='{' '.join(commands)}' "
        f"fill='none' stroke='#000000' stroke-width='1.2'"
        f"{_relation_path_attrs(relation)} />"
    )


def _node_center(node: SceneNode) -> tuple[float, float]:
    x1, y1, x2, y2 = node.bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _bbox_anchor_point(bbox: list[int], toward: tuple[float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    tx, ty = toward
    dx = tx - cx
    dy = ty - cy
    if abs(dx) >= abs(dy):
        return (float(x2), cy) if dx >= 0 else (float(x1), cy)
    return (cx, float(y2)) if dy >= 0 else (cx, float(y1))


def _render_node_fragment(
    node,
    region_map: dict[str, RegionVectorResult],
    stroke_map: dict[str, StrokeVectorResult],
) -> str | None:
    group_id = build_svg_group_id(node.id)
    if node.id in region_map:
        inner = region_map[node.id].svg_fragment
    elif node.id in stroke_map:
        inner = f"<path id='{node.id}' d='{stroke_map[node.id].svg_fragment}' fill='none' stroke='#000000' />"
    elif node.type == "text" and node.text_content:
        x1, y1, x2, y2 = node.bbox
        font_size = max(y2 - y1 - 4, 10)
        baseline_y = y2
        inner = (
            f"<text id='{node.id}' x='{x1}' y='{baseline_y}' "
            f"font-family='Arial' font-size='{font_size}' fill='{node.stroke or '#000000'}'>"
            f"{escape(node.text_content)}</text>"
        )
    else:
        return None
    role_attr = f" data-component-role='{node.component_role}'" if getattr(node, 'component_role', None) else ""
    shape_attr = f" data-shape-hint='{node.shape_hint}'" if getattr(node, 'shape_hint', None) else ""
    return f"<g id='{group_id}' data-node-type='{node.type}'{role_attr}{shape_attr}>{inner}</g>"


def _shape_attrs(
    group: SceneGroup,
    relation: SceneRelation | None = None,
    obj: SceneObject | None = None,
) -> str:
    parts: list[str] = []
    if group.shape_type:
        parts.append(f"data-shape-type='{group.shape_type}'")
    if group.direction:
        parts.append(f"data-direction='{group.direction}'")
    if obj is not None:
        parts.append(f"data-object-id='{obj.id}'")
        parts.append(f"data-object-type='{obj.object_type}'")
    if relation is not None:
        parts.append(f"data-relation-id='{relation.id}'")
        parts.append(f"data-relation-type='{relation.relation_type}'")
    if not parts:
        return ""
    return " " + " ".join(parts)



def _contains_pure_black_fill(fragment: str) -> bool:
    lowered = fragment.lower()
    return (
        "fill='#000000'" in lowered
        or 'fill="#000000"' in lowered
        or "fill='black'" in lowered
        or 'fill="black"' in lowered
    )


def _should_drop_pure_black_region_fragment(fragment: str) -> bool:
    lowered = fragment.lower()
    if not _contains_pure_black_fill(lowered):
        return False
    if any(token in lowered for token in ["class='edge'", 'class="edge"', "class='edge-arrow'", 'class="edge-arrow"', "class='node'", 'class="node"', '<text', "data-node-type='stroke'", 'data-node-type="stroke"']):
        return False
    return any(
        token in lowered
        for token in [
            "class='region'",
            'class="region"',
            "data-node-type='region'",
            'data-node-type="region"',
            "id='region-",
            'id="region-',
            "id='panel-region-",
            'id="panel-region-',
        ]
    )


def _relation_path_attrs(relation: SceneRelation | None) -> str:
    if relation is None:
        return ""
    return (
        f" data-relation-id='{relation.id}'"
        f" data-relation-type='{relation.relation_type}'"
    )

