"""Helpers for hierarchical contour tracing and lightweight polygon smoothing."""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np


DEFAULT_POLY_EPSILON_RATIO = 0.012
DEFAULT_SHORT_EDGE_THRESHOLD = 3.0
DEFAULT_COLLINEAR_SINE_THRESHOLD = 0.08


def subtree_indices(root_index: int, hierarchy: np.ndarray) -> list[int]:
    """Return the contour subtree rooted at ``root_index``."""

    collected: list[int] = []
    stack = [root_index]
    while stack:
        current = stack.pop()
        collected.append(current)
        child = hierarchy[current][2]
        while child != -1:
            stack.append(child)
            child = hierarchy[child][0]
    return collected


def select_root_indices(
    contours: list[np.ndarray],
    hierarchy: np.ndarray,
    image_shape: tuple[int, int],
    *,
    min_root_area: float = 45.0,
    max_roots: int = 12,
    relative_score_min: float = 0.18,
) -> list[int]:
    """Select dominant root contours while suppressing much smaller detached roots."""

    roots: list[tuple[float, int]] = []
    for index, contour in enumerate(contours):
        if hierarchy[index][3] != -1:
            continue
        area = cv2.contourArea(contour)
        if area < min_root_area:
            continue
        roots.append((_root_score(index, contours, hierarchy, image_shape), index))

    roots.sort(reverse=True)
    if not roots:
        return []

    best_score = roots[0][0]
    selected = [
        index
        for score, index in roots[:max_roots]
        if score >= best_score * relative_score_min
    ]
    return selected or [roots[0][1]]


def approximate_contour(
    contour: np.ndarray,
    *,
    epsilon_ratio: float = DEFAULT_POLY_EPSILON_RATIO,
    min_epsilon: float = 1.0,
) -> np.ndarray:
    """Approximate and smooth a closed contour."""

    perimeter = cv2.arcLength(contour, True)
    epsilon = max(min_epsilon, perimeter * epsilon_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = approx.reshape(-1, 2) if len(approx) >= 3 else contour.reshape(-1, 2)
    return smooth_closed_polygon(points)


def smooth_closed_polygon(
    points: np.ndarray,
    *,
    short_edge_threshold: float = DEFAULT_SHORT_EDGE_THRESHOLD,
    collinear_sine_threshold: float = DEFAULT_COLLINEAR_SINE_THRESHOLD,
) -> np.ndarray:
    """Drop tiny zig-zag edges and nearly collinear vertices from a closed polygon."""

    current = _dedupe_points(points)
    if len(current) <= 3:
        return current

    changed = True
    while changed and len(current) > 3:
        changed = False
        next_points: list[np.ndarray] = []
        count = len(current)
        for index in range(count):
            prev_point = current[(index - 1) % count]
            point = current[index]
            next_point = current[(index + 1) % count]

            prev_vec = point - prev_point
            next_vec = next_point - point
            prev_len = float(np.linalg.norm(prev_vec))
            next_len = float(np.linalg.norm(next_vec))
            if prev_len == 0.0 or next_len == 0.0:
                changed = True
                continue

            if min(prev_len, next_len) <= short_edge_threshold:
                changed = True
                continue

            sin_theta = abs(_cross_2d(prev_vec, next_vec)) / max(prev_len * next_len, 1e-6)
            dot = float(np.dot(prev_vec, next_vec))
            if dot > 0.0 and sin_theta <= collinear_sine_threshold:
                changed = True
                continue

            next_points.append(point)

        if len(next_points) < 3:
            break
        current = np.asarray(next_points, dtype=np.int32)

    return current


def contour_path_commands(
    contour: np.ndarray,
    offset_x: int,
    offset_y: int,
    *,
    epsilon_ratio: float = DEFAULT_POLY_EPSILON_RATIO,
    min_epsilon: float = 1.0,
) -> str:
    """Convert a contour into an SVG path command string."""

    points = approximate_contour(contour, epsilon_ratio=epsilon_ratio, min_epsilon=min_epsilon)
    if len(points) == 0:
        return ""
    commands = [f"M {int(points[0][0] + offset_x)} {int(points[0][1] + offset_y)}"]
    for point in points[1:]:
        commands.append(f"L {int(point[0] + offset_x)} {int(point[1] + offset_y)}")
    commands.append("Z")
    return " ".join(commands)


def collect_compound_subpaths(
    contours: list[np.ndarray],
    hierarchy: np.ndarray,
    root_indices: Iterable[int],
    *,
    offset_x: int,
    offset_y: int,
    min_area: float = 20.0,
    epsilon_ratio: float = DEFAULT_POLY_EPSILON_RATIO,
    min_epsilon: float = 1.0,
) -> list[str]:
    """Collect all meaningful contour subpaths under selected roots."""

    selected: set[int] = set()
    commands: list[str] = []
    for root_index in root_indices:
        for index in subtree_indices(root_index, hierarchy):
            if index in selected:
                continue
            selected.add(index)
            contour = contours[index]
            if cv2.contourArea(contour) < min_area:
                continue
            path = contour_path_commands(
                contour,
                offset_x,
                offset_y,
                epsilon_ratio=epsilon_ratio,
                min_epsilon=min_epsilon,
            )
            if path:
                commands.append(path)
    return commands


def _root_score(
    root_index: int,
    contours: list[np.ndarray],
    hierarchy: np.ndarray,
    image_shape: tuple[int, int],
) -> float:
    root = contours[root_index]
    area = cv2.contourArea(root)
    x, y, width, height = cv2.boundingRect(root)
    image_height, image_width = image_shape
    center_x = x + (width / 2.0)
    center_y = y + (height / 2.0)
    distance_from_center = ((center_x - image_width / 2.0) ** 2 + (center_y - image_height / 2.0) ** 2) ** 0.5
    max_distance = max((image_width ** 2 + image_height ** 2) ** 0.5 / 2.0, 1.0)
    center_bonus = 1.0 - min(distance_from_center / max_distance, 1.0)
    descendants = subtree_indices(root_index, hierarchy)
    child_bonus = max(len(descendants) - 1, 0) * 12.0
    return area + child_bonus + center_bonus * 25.0


def _dedupe_points(points: np.ndarray) -> np.ndarray:
    deduped: list[np.ndarray] = []
    for point in np.asarray(points, dtype=np.int32):
        if deduped and np.array_equal(point, deduped[-1]):
            continue
        deduped.append(point)
    if len(deduped) > 1 and np.array_equal(deduped[0], deduped[-1]):
        deduped.pop()
    return np.asarray(deduped, dtype=np.int32)


def _cross_2d(left: np.ndarray, right: np.ndarray) -> float:
    return float(left[0] * right[1] - left[1] * right[0])
