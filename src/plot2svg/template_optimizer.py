"""Deterministic cleanup helpers for layout template components."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def dedupe_text_placeholders(
    entries: list[dict[str, Any]],
    overlap_threshold: float = 0.82,
) -> list[dict[str, Any]]:
    """Remove highly overlapping duplicate text entries, keeping higher confidence."""

    result: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get('component_type') != 'text':
            result.append(deepcopy(entry))
            continue
        candidate = deepcopy(entry)
        duplicate_index = _find_duplicate_text(result, candidate, overlap_threshold)
        if duplicate_index is None:
            result.append(candidate)
            continue
        current = result[duplicate_index]
        keep_new = float(candidate.get('confidence') or 0.0) > float(current.get('confidence') or 0.0)
        kept = candidate if keep_new else current
        dropped = current if keep_new else candidate
        hints = dict(kept.get('optimization_hints') or {})
        deduped_from = list(hints.get('deduped_from') or [])
        deduped_from.append(str(dropped.get('display_id') or dropped.get('source_id') or 'unknown'))
        hints['deduped_from'] = deduped_from
        kept['optimization_hints'] = hints
        result[duplicate_index] = kept
    return result


def snap_aligned_bboxes(entries: list[dict[str, Any]], tolerance: int = 4) -> list[dict[str, Any]]:
    """Snap near-aligned left edges to the earliest matching coordinate."""

    snapped: list[dict[str, Any]] = []
    anchors: list[int] = []
    for entry in entries:
        item = deepcopy(entry)
        bbox = _bbox(item)
        if bbox is None:
            snapped.append(item)
            continue
        left = bbox[0]
        anchor = next((value for value in anchors if abs(left - value) <= tolerance), None)
        if anchor is None:
            anchors.append(left)
            snapped.append(item)
            continue
        if anchor != left:
            delta = anchor - left
            bbox[0] = anchor
            bbox[2] += delta
            item['bbox'] = bbox
            hints = dict(item.get('optimization_hints') or {})
            hints['snapped_left_to'] = anchor
            item['optimization_hints'] = hints
        snapped.append(item)
    return snapped


def normalize_component_z_order(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return components in conservative visual stacking order."""

    return sorted(
        [deepcopy(entry) for entry in entries],
        key=lambda entry: (_z_rank(str(entry.get('component_type') or '')), str(entry.get('display_id') or '')),
    )


def optimize_template_components(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply deterministic template cleanup passes in a stable order."""

    return normalize_component_z_order(snap_aligned_bboxes(dedupe_text_placeholders(entries)))


def apply_template_optimization(manifest: dict[str, Any], mode: str) -> dict[str, Any]:
    """Return a manifest copy with deterministic template cleanup applied."""

    optimized = deepcopy(manifest)
    components = [deepcopy(entry) for entry in manifest.get('components', [])]
    if mode == 'none':
        optimized['components'] = components
        return optimized
    if mode != 'deterministic':
        raise ValueError(f'Unsupported template optimization: {mode}')
    optimized_components = optimize_template_components(components)
    optimized['components'] = optimized_components
    summary = dict(optimized.get('summary') or {})
    summary['component_count'] = len(optimized_components)
    summary['template_optimization'] = mode
    optimized['summary'] = summary
    return optimized

def _find_duplicate_text(
    entries: list[dict[str, Any]],
    candidate: dict[str, Any],
    overlap_threshold: float,
) -> int | None:
    candidate_bbox = _bbox(candidate)
    if candidate_bbox is None:
        return None
    for index, entry in enumerate(entries):
        if entry.get('component_type') != 'text':
            continue
        entry_bbox = _bbox(entry)
        if entry_bbox is None:
            continue
        if _overlap_ratio(candidate_bbox, entry_bbox) >= overlap_threshold:
            return index
    return None


def _bbox(entry: dict[str, Any]) -> list[int] | None:
    raw = entry.get('bbox')
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    return [int(value) for value in raw]


def _overlap_ratio(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    return intersection / max(min(_area(left), _area(right)), 1)


def _area(bbox: list[int]) -> int:
    return max(bbox[2] - bbox[0], 1) * max(bbox[3] - bbox[1], 1)


def _z_rank(component_type: str) -> int:
    if component_type in {'region', 'raster'}:
        return 0
    if component_type in {'icon', 'node'}:
        return 1
    if component_type in {'edge', 'stroke'}:
        return 2
    if component_type == 'group':
        return 3
    if component_type == 'text':
        return 4
    return 5