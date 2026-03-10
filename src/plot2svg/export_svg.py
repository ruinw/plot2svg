"""Grouped SVG export helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .scene_graph import SceneGraph, SceneGroup
from .vectorize_region import RegionVectorResult
from .vectorize_stroke import StrokeVectorResult

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

    grouped_node_ids = {child_id for group in scene_graph.groups for child_id in group.child_ids}
    groups: list[str] = []

    for group in scene_graph.groups:
        child_fragments: list[str] = []
        for node in sorted(_resolve_group_nodes(scene_graph, group.child_ids), key=lambda item: item.z_index):
            fragment = _render_node_fragment(node, region_map, stroke_map)
            if fragment is None:
                continue
            child_fragments.append(fragment)
        if not child_fragments:
            continue
        shape_attrs = _shape_attrs(group)
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

    svg_content = "\n".join(
        [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{scene_graph.width}' height='{scene_graph.height}' viewBox='0 0 {scene_graph.width} {scene_graph.height}'>",
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
        baseline_y = y1 + font_size
        inner = (
            f"<text id='{node.id}' x='{x1}' y='{baseline_y}' "
            f"font-size='{font_size}' fill='{node.stroke or '#000000'}'>{node.text_content}</text>"
        )
    else:
        return None
    role_attr = f" data-component-role='{node.component_role}'" if getattr(node, 'component_role', None) else ""
    return f"<g id='{group_id}' data-node-type='{node.type}'{role_attr}>{inner}</g>"


def _shape_attrs(group: SceneGroup) -> str:
    parts: list[str] = []
    if group.shape_type:
        parts.append(f"data-shape-type='{group.shape_type}'")
    if group.direction:
        parts.append(f"data-direction='{group.direction}'")
    if not parts:
        return ""
    return " " + " ".join(parts)
