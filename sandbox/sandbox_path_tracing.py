from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random

import cv2
import numpy as np
from skimage.morphology import skeletonize


# =============================
# Tunable parameters
# =============================
SATURATION_MAX = 90
VALUE_MAX = 185
GRAY_THRESHOLD = 190
DILATE_KERNEL = 3
DILATE_ITERATIONS = 1
MIN_PATH_POINTS = 8
SIMPLIFY_TOLERANCE = 1.0
SVG_STROKE_WIDTH = 1.4

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / 'A.png'
DEBUG_PATHS = BASE_DIR / 'debug_03_paths.png'
OUTPUT_SVG = BASE_DIR / 'slice_A_v2.svg'


@dataclass
class TracedPath:
    points: list[tuple[int, int]]  # (y, x)


def main() -> None:
    image = load_image(INPUT_PATH)
    mask = build_line_mask(image)
    skeleton = build_skeleton(mask)
    paths = trace_skeleton_to_paths(skeleton)
    render_paths_debug(image, paths, DEBUG_PATHS)
    write_svg(paths, image.shape[1], image.shape[0], OUTPUT_SVG)
    print(f'Traced {len(paths)} paths from {INPUT_PATH.name}')
    print(f'Generated: {DEBUG_PATHS.name}, {OUTPUT_SVG.name}')


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f'Failed to load {path}')
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        bgr = image[:, :, :3].astype(np.float32)
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        white = np.full_like(bgr, 255.0)
        composited = bgr * alpha + white * (1.0 - alpha)
        return np.clip(composited, 0, 255).astype(np.uint8)
    return image[:, :, :3]


def build_line_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    low_sat_dark = cv2.inRange(hsv, np.array([0, 0, 0], dtype=np.uint8), np.array([180, SATURATION_MAX, VALUE_MAX], dtype=np.uint8))
    _, gray_mask = cv2.threshold(gray, GRAY_THRESHOLD, 255, cv2.THRESH_BINARY_INV)
    mask = cv2.bitwise_and(low_sat_dark, gray_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (DILATE_KERNEL, DILATE_KERNEL))
    mask = cv2.dilate(mask, kernel, iterations=DILATE_ITERATIONS)
    return mask


def build_skeleton(mask: np.ndarray) -> np.ndarray:
    bool_mask = mask > 0
    skeleton_bool = skeletonize(bool_mask)
    return (skeleton_bool.astype(np.uint8) * 255)


def trace_skeleton_to_paths(skeleton_mask: np.ndarray) -> list[TracedPath]:
    points = np.column_stack(np.where(skeleton_mask > 0))
    point_set = set(map(tuple, points))
    if not point_set:
        return []

    neighbor_map = {point: get_neighbors(point, point_set) for point in point_set}
    endpoints = [point for point, neighbors in neighbor_map.items() if len(neighbors) == 1]
    junctions = {point for point, neighbors in neighbor_map.items() if len(neighbors) > 2}
    remaining = set(point_set)
    paths: list[TracedPath] = []

    starts = endpoints[:] if endpoints else [next(iter(point_set))]
    for start in starts:
        if start not in remaining:
            continue
        path = trace_single_path(start, neighbor_map, remaining, junctions)
        if len(path) >= MIN_PATH_POINTS:
            simplified = simplify_polyline(path, tolerance=SIMPLIFY_TOLERANCE)
            if len(simplified) >= 2:
                paths.append(TracedPath(simplified))

    while remaining:
        start = next(iter(remaining))
        path = trace_single_path(start, neighbor_map, remaining, junctions)
        if len(path) >= MIN_PATH_POINTS:
            simplified = simplify_polyline(path, tolerance=SIMPLIFY_TOLERANCE)
            if len(simplified) >= 2:
                paths.append(TracedPath(simplified))

    paths.sort(key=lambda item: item.points[0][0])
    return paths


def trace_single_path(
    start: tuple[int, int],
    neighbor_map: dict[tuple[int, int], list[tuple[int, int]]],
    remaining: set[tuple[int, int]],
    junctions: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    path = [start]
    remaining.discard(start)
    prev: tuple[int, int] | None = None
    curr = start

    while True:
        next_candidates = [neighbor for neighbor in neighbor_map[curr] if neighbor != prev and neighbor in remaining]
        if not next_candidates:
            break
        next_node = choose_next_neighbor(curr, prev, next_candidates)
        path.append(next_node)
        remaining.discard(next_node)
        prev, curr = curr, next_node
        if curr in junctions:
            break
    return path


def choose_next_neighbor(
    curr: tuple[int, int],
    prev: tuple[int, int] | None,
    neighbors: list[tuple[int, int]],
) -> tuple[int, int]:
    if prev is None or len(neighbors) == 1:
        return neighbors[0]
    py, px = prev
    cy, cx = curr
    direction = (cy - py, cx - px)

    def score(neighbor: tuple[int, int]) -> tuple[float, float]:
        ny, nx = neighbor
        step = (ny - cy, nx - cx)
        dot = direction[0] * step[0] + direction[1] * step[1]
        dist = math.hypot(step[0], step[1])
        return (-dot, dist)

    return sorted(neighbors, key=score)[0]


def get_neighbors(point: tuple[int, int], point_set: set[tuple[int, int]]) -> list[tuple[int, int]]:
    y, x = point
    neighbors: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            candidate = (y + dy, x + dx)
            if candidate in point_set:
                neighbors.append(candidate)
    return neighbors


def simplify_polyline(points: list[tuple[int, int]], tolerance: float = 1.0) -> list[tuple[int, int]]:
    if len(points) < 3:
        return points
    point_arrays = [np.array(point, dtype=np.float32) for point in points]
    simplified = [points[0]]
    for index in range(1, len(points) - 1):
        last = np.array(simplified[-1], dtype=np.float32)
        curr = point_arrays[index]
        next_point = point_arrays[index + 1]
        baseline = next_point - last
        baseline_norm = np.linalg.norm(baseline)
        if baseline_norm <= 1e-6:
            simplified.append(points[index])
            continue
        offset = last - curr
        cross_z = float(baseline[0] * offset[1] - baseline[1] * offset[0])
        distance = abs(cross_z) / baseline_norm
        if distance > tolerance:
            simplified.append(points[index])
    simplified.append(points[-1])
    return dedupe_points(simplified)


def dedupe_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    deduped: list[tuple[int, int]] = []
    for point in points:
        if not deduped or deduped[-1] != point:
            deduped.append(point)
    return deduped


def render_paths_debug(image: np.ndarray, paths: list[TracedPath], output_path: Path) -> None:
    overlay = image.copy()
    rng = random.Random(17)
    for index, path in enumerate(paths):
        color = (rng.randint(40, 255), rng.randint(40, 255), rng.randint(40, 255))
        xy_points = [(point[1], point[0]) for point in path.points]
        for left, right in zip(xy_points, xy_points[1:]):
            cv2.line(overlay, left, right, color, 2, cv2.LINE_AA)
        start = xy_points[0]
        end = xy_points[-1]
        cv2.circle(overlay, start, 2, (0, 0, 255), -1)
        cv2.circle(overlay, end, 2, (0, 255, 255), -1)
        cv2.putText(overlay, str(index), start, cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    cv2.imwrite(str(output_path), overlay)


def write_svg(paths: list[TracedPath], width: int, height: int, output_path: Path) -> None:
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#ffffff' />",
    ]
    for index, path in enumerate(paths):
        pts = ' '.join(f'{point[1]},{point[0]}' for point in path.points)
        parts.append(
            f"<polyline id='path-{index:03d}' points='{pts}' fill='none' stroke='#374151' stroke-width='{SVG_STROKE_WIDTH}' stroke-linecap='round' stroke-linejoin='round' />"
        )
    parts.append('</svg>')
    output_path.write_text('\n'.join(parts), encoding='utf-8')


if __name__ == '__main__':
    main()
