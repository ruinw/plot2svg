"""Structural metrics for Plot2SVG output artifacts."""

from __future__ import annotations

import re
from typing import Any


def compute_artifact_metrics(scene_graph: dict[str, Any], svg_content: str) -> dict[str, int]:
    """Compute repeatable editability metrics from scene graph JSON and SVG text."""

    nodes = scene_graph.get('nodes', [])
    return {
        'node_count': len(nodes),
        'text_count': _count_nodes(nodes, 'text'),
        'region_count': _count_nodes(nodes, 'region'),
        'stroke_count': _count_nodes(nodes, 'stroke'),
        'icon_count': len(scene_graph.get('icon_objects', [])),
        'raster_fallback_count': len(scene_graph.get('raster_objects', [])),
        'graph_edge_count': len(scene_graph.get('graph_edges', [])),
        'svg_text_count': _count_tags(svg_content, 'text'),
        'svg_shape_count': sum(_count_tags(svg_content, tag) for tag in ('rect', 'circle', 'ellipse')),
        'svg_path_count': _count_tags(svg_content, 'path'),
        'svg_image_count': _count_tags(svg_content, 'image'),
    }


def _count_nodes(nodes: list[dict[str, Any]], node_type: str) -> int:
    return sum(1 for node in nodes if node.get('type') == node_type)


def _count_tags(svg_content: str, tag_name: str) -> int:
    return len(re.findall(rf'<{tag_name}\b', svg_content, flags=re.IGNORECASE))