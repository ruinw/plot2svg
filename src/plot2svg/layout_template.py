"""Debug layout template SVG generation."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

_TEMPLATE_STYLE = """
<style>
.template-placeholder { fill: rgba(30, 144, 255, 0.055); stroke: #1e90ff; stroke-width: 1; stroke-dasharray: 4 3; }
.template-label { font-family: Arial, sans-serif; font-size: 10px; fill: #0f172a; pointer-events: none; }
.template-edge { fill: none; stroke: #f97316; stroke-width: 1.2; stroke-dasharray: 3 2; }
</style>
""".strip()


def build_layout_template_svg(manifest: dict[str, Any]) -> str:
    """Render a debug-only SVG template from a component manifest."""

    canvas = manifest.get('canvas', {})
    width = int(canvas.get('width', 0))
    height = int(canvas.get('height', 0))
    elements: list[str] = []
    for entry in manifest.get('components', []):
        bbox = _bbox(entry)
        if bbox is None:
            continue
        template_id = escape(str(entry.get('template_id') or f"tpl-{entry.get('display_id', 'component')}"), quote=True)
        display_id = escape(str(entry.get('display_id', '')), quote=True)
        source_id = escape(str(entry.get('source_id', '')), quote=True)
        component_type = escape(str(entry.get('component_type', 'component')), quote=True)
        x1, y1, x2, y2 = bbox
        box_width = max(x2 - x1, 1)
        box_height = max(y2 - y1, 1)
        if entry.get('component_type') == 'edge':
            elements.append(
                f"  <path id='{template_id}' class='template-placeholder template-edge' "
                f"data-display-id='{display_id}' data-source-id='{source_id}' "
                f"d='M {x1} {y1} L {x2} {y2}' />"
            )
        else:
            elements.append(
                f"  <rect id='{template_id}' class='template-placeholder template-{component_type}' "
                f"data-display-id='{display_id}' data-source-id='{source_id}' "
                f"x='{x1}' y='{y1}' width='{box_width}' height='{box_height}' />"
            )
        elements.append(
            f"  <text class='template-label' x='{x1}' y='{max(y1 - 3, 10)}'>{display_id}</text>"
        )
    return "\n".join([
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        _TEMPLATE_STYLE,
        *elements,
        "</svg>",
    ])


def write_layout_template_svg(manifest: dict[str, Any], path: Path) -> None:
    """Write the debug layout template SVG artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_layout_template_svg(manifest), encoding='utf-8')


def _bbox(entry: dict[str, Any]) -> tuple[int, int, int, int] | None:
    raw = entry.get('bbox')
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    x1, y1, x2, y2 = [int(value) for value in raw]
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2