"""Blind-test benchmarking helpers for generalized pipeline evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .api import Plot2SvgEngine


SUPPORTED_IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp'}


def run_blind_test_benchmark(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    engine: Plot2SvgEngine | Any | None = None,
    skip_existing: bool = False,
    image_names: list[str] | None = None,
) -> dict[str, Any]:
    """Run the Plot2SVG pipeline over a blind-test set and emit a Markdown report."""

    engine = engine or Plot2SvgEngine()
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    selected_names = set(image_names or [])
    image_paths = sorted(
        path for path in input_root.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        and (not selected_names or path.name in selected_names)
    ) if input_root.exists() else []

    results: list[dict[str, Any]] = []
    for image_path in image_paths:
        image_output_dir = output_root / image_path.stem
        if skip_existing:
            cached_scene_graph_path = image_output_dir / 'scene_graph.json'
            cached_svg_path = image_output_dir / 'final.svg'
            if cached_scene_graph_path.exists() and cached_svg_path.exists():
                scene_graph = json.loads(cached_scene_graph_path.read_text(encoding='utf-8'))
                results.append(_summarize_result(image_path.name, True, scene_graph, None))
                continue
        payload = engine.process_image(image_path=image_path, output_dir=image_output_dir)
        scene_graph = payload.get('scene_graph') or {}
        result = _summarize_result(image_path.name, payload.get('status') == 'ok', scene_graph, payload.get('error'))
        results.append(result)

    report_markdown = _build_markdown_report(input_root, results)
    report_path = output_root / 'blind_test_report.md'
    report_path.write_text(report_markdown, encoding='utf-8')
    return {
        'report_path': report_path,
        'report_markdown': report_markdown,
        'results': results,
    }


def _summarize_result(
    image_name: str,
    ok: bool,
    scene_graph: dict[str, Any],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    edges = scene_graph.get('graph_edges', [])
    total_edges = len(edges)
    orthogonal_edges = sum(1 for edge in edges if _is_orthogonal(edge.get('path') or []))
    route_degraded = sum(1 for edge in edges if (edge.get('metadata') or {}).get('route_degraded'))
    icon_objects = len(scene_graph.get('icon_objects', []))
    raster_candidate_residual = sum(1 for node in scene_graph.get('nodes', []) if node.get('shape_hint') == 'raster_candidate')
    return {
        'image': image_name,
        'status': 'ok' if ok else 'error',
        'total_edges': total_edges,
        'orthogonal_edges': orthogonal_edges,
        'orthogonal_ratio': (orthogonal_edges / total_edges) if total_edges else 0.0,
        'route_degraded': route_degraded,
        'icon_objects': icon_objects,
        'raster_candidate_residual': raster_candidate_residual,
        'error': (error or {}).get('message'),
    }


def _is_orthogonal(points: list[list[float]]) -> bool:
    if len(points) < 2:
        return False
    return all(left[0] == right[0] or left[1] == right[1] for left, right in zip(points, points[1:]))


def _build_markdown_report(input_root: Path, results: list[dict[str, Any]]) -> str:
    lines = [
        '# Plot2SVG Blind Test Report',
        '',
        f"- Input set: `{input_root}`",
        f"- Images processed: `{len(results)}`",
        '',
        '| Image | Status | total_edges | orthogonal_edges | orthogonal_ratio | route_degraded | icon_objects | raster_candidate_residual | Error |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
    ]
    for result in results:
        lines.append(
            f"| {result['image']} | {result['status']} | {result['total_edges']} | {result['orthogonal_edges']} | "
            f"{result['orthogonal_ratio']:.2%} | {result['route_degraded']} | {result['icon_objects']} | "
            f"{result['raster_candidate_residual']} | {result['error'] or ''} |"
        )
    if not results:
        lines.append('| (none) | skipped | 0 | 0 | 0.00% | 0 | 0 | 0 | input directory missing or empty |')
    return '\n'.join(lines) + '\n'
