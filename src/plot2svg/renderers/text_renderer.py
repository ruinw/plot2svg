"""Text SVG rendering helpers."""

from __future__ import annotations

from html import escape
import re

from ..color_utils import _is_light_container_color
from ..scene_graph import RegionObject, SceneGraph, SceneNode
from .common import bbox_gap, bbox_overlap


def text_nodes(scene_graph: SceneGraph) -> list[SceneNode]:
    return [
        node
        for node in scene_graph.nodes
        if node.type == 'text' and (node.text_content or '').strip()
    ]


def render_text_node(node: SceneNode) -> str | None:
    if not node.text_content:
        return None
    x1, y1, _x2, y2 = node.bbox
    font_size = max(y2 - y1 - 4, 10)
    baseline_y = y2
    lines = [line for line in node.text_content.splitlines() if line.strip()]
    if len(lines) <= 1:
        return (
            f"<text id='{node.id}' class='text' x='{x1}' y='{baseline_y}' "
            f"font-family='Arial' font-size='{font_size}' fill='{node.stroke or '#000000'}'>"
            f"{escape(node.text_content)}</text>"
        )
    line_height = max((y2 - y1) / max(len(lines), 1), font_size * 0.95)
    first_baseline = y1 + line_height
    tspans = [f"<tspan x='{x1}' y='{first_baseline:.1f}'>{escape(lines[0])}</tspan>"]
    for line in lines[1:]:
        tspans.append(f"<tspan x='{x1}' dy='{line_height:.1f}'>{escape(line)}</tspan>")
    return (
        f"<text id='{node.id}' class='text' x='{x1}' y='{baseline_y}' "
        f"font-family='Arial' font-size='{font_size}' fill='{node.stroke or '#000000'}'>"
        f"{''.join(tspans)}</text>"
    )


def text_overlaps_template_exclusion(text_node: SceneNode, template_bboxes: list[list[int]]) -> bool:
    text_bbox = text_node.bbox
    text_center_y = (text_bbox[1] + text_bbox[3]) / 2.0
    text_center_x = (text_bbox[0] + text_bbox[2]) / 2.0
    axis_like = is_template_axis_text(text_node.text_content or '')
    for bbox in template_bboxes:
        if bbox_overlap(text_bbox, bbox) > 0.0:
            return True
        gap = bbox_gap(text_bbox, bbox)
        if gap <= 15:
            return True
        if axis_like and gap <= 25:
            return True
        if not axis_like:
            continue
        vertically_aligned = (bbox[1] - 25) <= text_center_y <= (bbox[3] + 25)
        horizontally_aligned = (bbox[0] - 25) <= text_center_x <= (bbox[2] + 25)
        left_axis_gap = bbox[0] - text_bbox[2]
        right_axis_gap = text_bbox[0] - bbox[2]
        bottom_axis_gap = text_bbox[1] - bbox[3]
        if vertically_aligned and 0 <= left_axis_gap <= 110:
            return True
        if vertically_aligned and 0 <= right_axis_gap <= 40:
            return True
        if horizontally_aligned and 0 <= bottom_axis_gap <= 40:
            return True
    return False


def is_template_axis_text(text_content: str) -> bool:
    lowered = text_content.strip().lower()
    if not lowered:
        return False
    if re.fullmatch(r'[\d.\s%+\-]+', lowered):
        return True
    if lowered in {'years', 'year', 'yr', 'yrs', 'months', 'month', 'days', 'day', 'time', 'time (years)'}:
        return True
    compact = re.sub(r'[^a-z0-9]+', ' ', lowered).strip()
    if compact and any(char.isdigit() for char in compact):
        tokens = [token for token in compact.split() if token]
        long_alpha_tokens = [token for token in tokens if token.isalpha() and len(token) >= 3]
        alpha_count = sum(1 for char in compact if char.isalpha())
        if not long_alpha_tokens and alpha_count <= 3:
            return True
    return False


def is_lightweight_text_container(node: SceneNode | None, region_obj: RegionObject | None) -> bool:
    if node is None or node.type != 'region':
        return False
    if 'container_shape' not in str(node.component_role or ''):
        return False
    shape_type = str((region_obj.metadata or {}).get('shape_type') or '') if region_obj is not None else ''
    if shape_type and shape_type != 'rectangle':
        return False
    fill = (region_obj.fill if region_obj is not None else node.fill) or ''
    stroke = (region_obj.stroke if region_obj is not None else node.stroke) or ''
    return _is_light_container_color(fill, stroke)


def text_overlap_score(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1)
    union = left_area + right_area - intersection
    return max(intersection / left_area, intersection / right_area, intersection / max(union, 1))
