"""Dense line reconstruction helpers for stroke-heavy regions."""

from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(slots=True)
class DenseLineReconstruction:
    """Reconstructed long lines extracted from a dense skeleton cluster."""

    lines: list[tuple[int, int, int, int]]
    hub: tuple[float, float]
    raw_count: int
    merged_count: int


def reconstruct_dense_lines(skeleton: np.ndarray) -> DenseLineReconstruction | None:
    """Merge fragmented skeleton segments into a smaller set of long lines."""

    raw_lines = _detect_lines(skeleton)
    if len(raw_lines) < 3:
        return None

    merged_lines = _merge_orientation_clusters(raw_lines)
    seed_lines = merged_lines or raw_lines
    hub = _estimate_hub(seed_lines, skeleton.shape[1], skeleton.shape[0])
    radial_lines = _cluster_radial_lines(seed_lines, hub)
    if len(radial_lines) < 3:
        return None
    return DenseLineReconstruction(
        lines=radial_lines,
        hub=hub,
        raw_count=len(raw_lines),
        merged_count=len(merged_lines),
    )


def render_line_mask(shape: tuple[int, int], lines: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Rasterize reconstructed lines into a debug/inpaint style mask."""

    mask = np.zeros(shape, dtype=np.uint8)
    for x1, y1, x2, y2 in lines:
        cv2.line(mask, (x1, y1), (x2, y2), 255, 2, cv2.LINE_AA)
    return mask


def line_length(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    return math.hypot(x2 - x1, y2 - y1)


def _normalize_line(line: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = line
    if (x1, y1) <= (x2, y2):
        return line
    return (x2, y2, x1, y1)


def _line_orientation(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _angular_gap(left: float, right: float, period: float = 180.0) -> float:
    gap = abs(left - right) % period
    return min(gap, period - gap)


def _line_rho(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    theta = math.atan2(y2 - y1, x2 - x1) + math.pi / 2.0
    return x1 * math.cos(theta) + y1 * math.sin(theta)


def _point_line_distance(point: tuple[int, int], line: tuple[int, int, int, int]) -> float:
    x0, y0 = point
    x1, y1, x2, y2 = line
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def _endpoint_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    left_points = [(left[0], left[1]), (left[2], left[3])]
    right_points = [(right[0], right[1]), (right[2], right[3])]
    return min(math.hypot(ax - bx, ay - by) for ax, ay in left_points for bx, by in right_points)


def _projection_interval(line: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = line
    direction = np.array([x2 - x1, y2 - y1], dtype=np.float32)
    length = float(np.hypot(direction[0], direction[1]))
    if length <= 1e-6:
        return 0.0, 0.0
    direction /= length
    p1 = float(direction[0] * x1 + direction[1] * y1)
    p2 = float(direction[0] * x2 + direction[1] * y2)
    return min(p1, p2), max(p1, p2)


def _interval_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    left_min, left_max = _projection_interval(left)
    right_min, right_max = _projection_interval(right)
    if left_max < right_min:
        return right_min - left_max
    if right_max < left_min:
        return left_min - right_max
    return 0.0


def _dedupe_lines(lines: list[tuple[int, int, int, int]], tolerance: int = 3) -> list[tuple[int, int, int, int]]:
    unique: list[tuple[int, int, int, int]] = []
    for line in lines:
        candidate = _normalize_line(line)
        if any(max(abs(a - b) for a, b in zip(candidate, existing)) <= tolerance for existing in unique):
            continue
        unique.append(candidate)
    return unique


def _detect_lines(skeleton: np.ndarray) -> list[tuple[int, int, int, int]]:
    candidates: list[tuple[int, int, int, int]] = []
    raw_hough = cv2.HoughLinesP(
        skeleton,
        rho=1,
        theta=np.pi / 180,
        threshold=16,
        minLineLength=18,
        maxLineGap=20,
    )
    if raw_hough is not None:
        for raw in raw_hough[:, 0, :]:
            candidate = _normalize_line(tuple(int(value) for value in raw.tolist()))
            if line_length(candidate) >= 18.0:
                candidates.append(candidate)

    if hasattr(cv2, 'createLineSegmentDetector'):
        detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
        detected = detector.detect(skeleton)[0]
        if detected is not None:
            for raw in detected[:, 0, :]:
                candidate = _normalize_line(tuple(int(round(value)) for value in raw.tolist()))
                if line_length(candidate) >= 14.0:
                    candidates.append(candidate)
    return _dedupe_lines(candidates)


def _cluster_by_orientation(
    lines: list[tuple[int, int, int, int]],
    angle_tolerance: float = 2.0,
) -> list[list[tuple[int, int, int, int]]]:
    if not lines:
        return []
    sorted_lines = sorted(lines, key=_line_orientation)
    clusters: list[list[tuple[int, int, int, int]]] = []
    current = [sorted_lines[0]]
    current_center = _line_orientation(sorted_lines[0])
    for line in sorted_lines[1:]:
        orientation = _line_orientation(line)
        if _angular_gap(orientation, current_center) <= angle_tolerance:
            current.append(line)
            current_center = sum(_line_orientation(item) for item in current) / len(current)
        else:
            clusters.append(current)
            current = [line]
            current_center = orientation
    clusters.append(current)
    return clusters


def _can_merge_lines(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    if _angular_gap(_line_orientation(left), _line_orientation(right)) > 2.0:
        return False
    if abs(_line_rho(left) - _line_rho(right)) > 12.0:
        return False
    distances = [
        _point_line_distance((left[0], left[1]), right),
        _point_line_distance((left[2], left[3]), right),
        _point_line_distance((right[0], right[1]), left),
        _point_line_distance((right[2], right[3]), left),
    ]
    if max(distances) > 8.0:
        return False
    return _endpoint_gap(left, right) <= 30.0 or _interval_gap(left, right) <= 30.0


def _merge_pair(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    points = np.array(
        [[left[0], left[1]], [left[2], left[3]], [right[0], right[1]], [right[2], right[3]]],
        dtype=np.float32,
    )
    vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
    direction = np.array([vx, vy], dtype=np.float32)
    center = np.array([x0, y0], dtype=np.float32)
    projections = (points - center) @ direction
    start = center + direction * projections.min()
    end = center + direction * projections.max()
    return _normalize_line(tuple(int(round(value)) for value in [start[0], start[1], end[0], end[1]]))


def _merge_orientation_clusters(lines: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for cluster in _cluster_by_orientation(lines):
        remaining = cluster[:]
        changed = True
        while changed:
            changed = False
            next_lines: list[tuple[int, int, int, int]] = []
            used = [False] * len(remaining)
            for index, current in enumerate(remaining):
                if used[index]:
                    continue
                candidate = current
                for follow in range(index + 1, len(remaining)):
                    if used[follow]:
                        continue
                    if _can_merge_lines(candidate, remaining[follow]):
                        candidate = _merge_pair(candidate, remaining[follow])
                        used[follow] = True
                        changed = True
                used[index] = True
                next_lines.append(candidate)
            remaining = next_lines
        merged.extend(remaining)
    merged.sort(key=line_length, reverse=True)
    return _dedupe_lines(merged, tolerance=2)


def _line_intersection(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> tuple[float, float] | None:
    x1, y1, x2, y2 = left
    x3, y3, x4, y4 = right
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-6:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denominator
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denominator
    return px, py


def _estimate_hub(lines: list[tuple[int, int, int, int]], width: int, height: int) -> tuple[float, float]:
    intersections: list[tuple[float, float]] = []
    for index, left in enumerate(lines):
        for right in lines[index + 1 :]:
            if _angular_gap(_line_orientation(left), _line_orientation(right)) < 8.0:
                continue
            point = _line_intersection(left, right)
            if point is None:
                continue
            px, py = point
            if -width * 0.25 <= px <= width * 1.25 and -height * 0.25 <= py <= height * 1.25:
                intersections.append(point)
    if intersections:
        best_point = intersections[0]
        best_score = -1
        for point in intersections:
            score = 0
            for other in intersections:
                if (point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2 <= 20.0 ** 2:
                    score += 1
            if score > best_score:
                best_point = point
                best_score = score
        return float(best_point[0]), float(best_point[1])

    endpoints = [
        (line[0], line[1])
        for line in lines
    ] + [
        (line[2], line[3])
        for line in lines
    ]
    best = min(
        endpoints,
        key=lambda point: sum(
            math.hypot(point[0] - other[0], point[1] - other[1]) for other in endpoints
        ),
    )
    return float(best[0]), float(best[1])


def _far_endpoint(
    line: tuple[int, int, int, int],
    hub: tuple[float, float],
) -> tuple[tuple[int, int], float]:
    points = [(line[0], line[1]), (line[2], line[3])]
    distances = [math.hypot(px - hub[0], py - hub[1]) for px, py in points]
    index = 0 if distances[0] >= distances[1] else 1
    return points[index], distances[index]


def _cluster_radial_lines(
    lines: list[tuple[int, int, int, int]],
    hub: tuple[float, float],
) -> list[tuple[int, int, int, int]]:
    items: list[dict[str, object]] = []
    for line in lines:
        far_point, far_distance = _far_endpoint(line, hub)
        if far_distance < 36.0:
            continue
        angle = (math.degrees(math.atan2(far_point[1] - hub[1], far_point[0] - hub[0])) + 360.0) % 360.0
        items.append({
            'angle': angle,
            'distance': far_distance,
            'point': far_point,
            'line': line,
        })
    if not items:
        return []

    items.sort(key=lambda item: float(item['angle']))
    clusters: list[list[dict[str, object]]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            center = sum(float(entry['angle']) for entry in cluster) / len(cluster)
            if abs(float(item['angle']) - center) <= 6.0:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    radial_lines: list[tuple[int, int, int, int]] = []
    hub_point = (int(round(hub[0])), int(round(hub[1])))
    for cluster in clusters:
        representative = max(cluster, key=lambda entry: float(entry['distance']))
        if float(representative['distance']) < 40.0:
            continue
        far_x, far_y = representative['point']
        radial_lines.append(_normalize_line((hub_point[0], hub_point[1], int(far_x), int(far_y))))

    radial_lines.sort(key=line_length, reverse=True)
    return _dedupe_lines(radial_lines, tolerance=2)
