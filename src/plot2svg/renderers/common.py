"""Shared geometry helpers for renderer modules."""

from __future__ import annotations

import math
from typing import Iterable


def bbox_overlap(left: list[int], right: list[int]) -> float:
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


def bbox_contains_point(bbox: list[int], x: float, y: float) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def expand_bbox(bbox: list[int], margin_x: int, margin_y: int) -> list[int]:
    return [bbox[0] - margin_x, bbox[1] - margin_y, bbox[2] + margin_x, bbox[3] + margin_y]


def union_bbox(bboxes: Iterable[list[int]]) -> list[int]:
    items = list(bboxes)
    return [
        min(bbox[0] for bbox in items),
        min(bbox[1] for bbox in items),
        max(bbox[2] for bbox in items),
        max(bbox[3] for bbox in items),
    ]


def bbox_gap(left: list[int], right: list[int]) -> int:
    horizontal_gap = max(left[0] - right[2], right[0] - left[2], 0)
    vertical_gap = max(left[1] - right[3], right[1] - left[3], 0)
    return max(horizontal_gap, vertical_gap)


def bbox_center(bbox: list[int]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def point_to_bbox_gap(point: list[float], bbox: list[int]) -> float:
    dx = max(float(bbox[0]) - float(point[0]), 0.0, float(point[0]) - float(bbox[2]))
    dy = max(float(bbox[1]) - float(point[1]), 0.0, float(point[1]) - float(bbox[3]))
    return math.hypot(dx, dy)


def nearest_bbox_boundary_point(point: list[float], bbox: list[int]) -> list[float]:
    x = min(max(float(point[0]), float(bbox[0])), float(bbox[2]))
    y = min(max(float(point[1]), float(bbox[1])), float(bbox[3]))
    candidates = [
        (abs(x - float(bbox[0])), [float(bbox[0]), y]),
        (abs(x - float(bbox[2])), [float(bbox[2]), y]),
        (abs(y - float(bbox[1])), [x, float(bbox[1])]),
        (abs(y - float(bbox[3])), [x, float(bbox[3])]),
    ]
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]
