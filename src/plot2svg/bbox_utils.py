"""Shared bounding-box helpers used by the pipeline."""

from __future__ import annotations

from .scene_graph import SceneNode


def _overlaps_existing_region(candidate: SceneNode, existing_regions: list[SceneNode]) -> bool:
    """Return whether the candidate substantially overlaps an existing region.

    Args:
        candidate: Candidate scene node.
        existing_regions: Existing region-like nodes.

    Returns:
        True when any existing region overlaps the candidate strongly.
    """
    for node in existing_regions:
        if _bbox_overlap(candidate.bbox, node.bbox) >= 0.7:
            return True
    return False


def _bbox_overlap(left: list[int], right: list[int]) -> float:
    """Compute overlap normalized by the smaller box area.

    Args:
        left: Left bbox in xyxy format.
        right: Right bbox in xyxy format.

    Returns:
        The overlap ratio relative to the smaller box.
    """
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


def _bbox_iou(left: list[int], right: list[int]) -> float:
    """Compute intersection-over-union for two bounding boxes.

    Args:
        left: Left bbox in xyxy format.
        right: Right bbox in xyxy format.

    Returns:
        The IoU score.
    """
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
    return intersection / max(union, 1)


def _contains_bbox(outer: list[int], inner: list[int], margin: int) -> bool:
    """Return whether one bbox contains another with an allowed margin.

    Args:
        outer: Outer bbox in xyxy format.
        inner: Inner bbox in xyxy format.
        margin: Extra tolerance applied on every side.

    Returns:
        True when the inner bbox fits within the expanded outer bbox.
    """
    return (
        outer[0] - margin <= inner[0]
        and outer[1] - margin <= inner[1]
        and outer[2] + margin >= inner[2]
        and outer[3] + margin >= inner[3]
    )


def _bbox_gap(left: list[int], right: list[int]) -> int:
    """Compute the maximum horizontal/vertical gap between two boxes.

    Args:
        left: Left bbox in xyxy format.
        right: Right bbox in xyxy format.

    Returns:
        The gap distance, or zero when the boxes touch/overlap.
    """
    horizontal_gap = max(left[0] - right[2], right[0] - left[2], 0)
    vertical_gap = max(left[1] - right[3], right[1] - left[3], 0)
    return max(horizontal_gap, vertical_gap)


def _matches_text_bbox(region_bbox: list[int], text_nodes: list[SceneNode]) -> bool:
    """Return whether a region bbox effectively matches any text bbox.

    Args:
        region_bbox: Region bbox in xyxy format.
        text_nodes: Candidate text nodes to compare against.

    Returns:
        True when the region strongly overlaps a text bbox.
    """
    region_area = max((region_bbox[2] - region_bbox[0]) * (region_bbox[3] - region_bbox[1]), 1)
    for text_node in text_nodes:
        if _bbox_iou(region_bbox, text_node.bbox) >= 0.8:
            return True
        overlap = _bbox_overlap(region_bbox, text_node.bbox)
        text_area = max((text_node.bbox[2] - text_node.bbox[0]) * (text_node.bbox[3] - text_node.bbox[1]), 1)
        if overlap >= 0.9 and region_area <= text_area * 2.6:
            return True
    return False


def _expand_bbox(bbox: list[int], width: int, height: int, margin: int) -> tuple[int, int, int, int]:
    """Expand a bbox by a symmetric margin while clamping to image bounds.

    Args:
        bbox: Source bbox in xyxy format.
        width: Image width.
        height: Image height.
        margin: Expansion margin in pixels.

    Returns:
        The expanded and clamped bbox.
    """
    x1, y1, x2, y2 = bbox
    return _clamp_bbox([x1 - margin, y1 - margin, x2 + margin, y2 + margin], width, height)


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    """Clamp a bbox to image bounds while preserving a non-zero area.

    Args:
        bbox: Source bbox in xyxy format.
        width: Image width.
        height: Image height.

    Returns:
        The clamped bbox.
    """
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2
