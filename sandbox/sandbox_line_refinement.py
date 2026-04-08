from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random
import re

import cv2
import numpy as np


# =============================
# Tunable parameters
# =============================
SNAP_DISTANCE = 3.5
SNAP_DISTANCE_RETRY = 5.5
COLLINEAR_JOIN_DISTANCE = 5.0
COLLINEAR_ANGLE_DEG = 5.0
RADIAL_CLUSTER_DEG = 4.0
RDP_EPSILON = 1.0
MIN_SEGMENT_SPAN = 6.0
MIN_BRANCH_SPAN = 18.0
HUB_LINE_MIN_SPAN = 20.0
MAX_OUTPUT_PATHS = 30
SVG_STROKE_WIDTH = 1.8

BASE_DIR = Path(__file__).resolve().parent
INPUT_IMAGE = BASE_DIR / "A.png"
INPUT_SVG = BASE_DIR / "slice_A_v2.svg"
DEBUG_OUTPUT = BASE_DIR / "debug_04_refined_structure.png"
OUTPUT_SVG = BASE_DIR / "slice_A_v3.svg"


@dataclass
class PolyPath:
    points: list[np.ndarray]

    def copy(self) -> "PolyPath":
        return PolyPath([point.copy() for point in self.points])

    @property
    def start(self) -> np.ndarray:
        return self.points[0]

    @property
    def end(self) -> np.ndarray:
        return self.points[-1]

    def span(self) -> float:
        return float(np.linalg.norm(self.end - self.start))

    def total_length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return float(
            sum(np.linalg.norm(right - left) for left, right in zip(self.points, self.points[1:]))
        )


def main() -> None:
    image = load_image(INPUT_IMAGE)
    raw_paths = parse_svg(INPUT_SVG)
    refined_paths, hub = refine_paths(raw_paths, image.shape[1], image.shape[0], SNAP_DISTANCE)

    if len(refined_paths) > MAX_OUTPUT_PATHS:
        refined_paths, hub = refine_paths(raw_paths, image.shape[1], image.shape[0], SNAP_DISTANCE_RETRY)

    render_debug(image, refined_paths, hub, DEBUG_OUTPUT)
    write_svg(refined_paths, image.shape[1], image.shape[0], OUTPUT_SVG)

    print(f"Loaded {len(raw_paths)} raw paths from {INPUT_SVG.name}")
    print(f"Refined to {len(refined_paths)} paths")
    print(f"Hub: ({hub[0]:.2f}, {hub[1]:.2f})")
    print(f"Generated: {DEBUG_OUTPUT.name}, {OUTPUT_SVG.name}")


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Failed to load {path}")
    return image


def parse_svg(path: Path) -> list[PolyPath]:
    text = path.read_text(encoding="utf-8")
    polyline_pattern = re.compile(r"<polyline[^>]*points='([^']+)'")
    path_pattern = re.compile(r"<path[^>]*d='([^']+)'")

    paths: list[PolyPath] = []
    for raw_points in polyline_pattern.findall(text):
        points = parse_points(raw_points)
        if len(points) >= 2:
            paths.append(PolyPath(points))

    for raw_d in path_pattern.findall(text):
        points = parse_path_d(raw_d)
        if len(points) >= 2:
            paths.append(PolyPath(points))

    if not paths:
        raise RuntimeError(f"No polyline/path elements found in {path}")
    return paths


def parse_points(raw_points: str) -> list[np.ndarray]:
    points: list[np.ndarray] = []
    for token in raw_points.split():
        x_str, y_str = token.split(",")
        points.append(np.array([float(x_str), float(y_str)], dtype=np.float32))
    return points


def parse_path_d(raw_d: str) -> list[np.ndarray]:
    tokens = re.findall(r"[ML]|-?\d+(?:\.\d+)?", raw_d)
    points: list[np.ndarray] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"M", "L"}:
            x = float(tokens[index + 1])
            y = float(tokens[index + 2])
            points.append(np.array([x, y], dtype=np.float32))
            index += 3
            continue
        index += 1
    return points


def refine_paths(
    raw_paths: list[PolyPath],
    width: int,
    height: int,
    snap_distance: float,
) -> tuple[list[PolyPath], np.ndarray]:
    merged = merge_close_paths(raw_paths, snap_distance)
    merged = merge_collinear_paths(merged, COLLINEAR_JOIN_DISTANCE, COLLINEAR_ANGLE_DEG)
    hub = estimate_hub(merged, width, height)
    radial = build_radial_paths(merged, hub)
    return radial, hub


def merge_close_paths(raw_paths: list[PolyPath], snap_distance: float) -> list[PolyPath]:
    paths = [path.copy() for path in raw_paths if path.total_length() >= MIN_SEGMENT_SPAN]
    changed = True
    while changed and len(paths) > 1:
        changed = False
        best_pair: tuple[int, int, tuple[bool, bool], float] | None = None
        for left_index in range(len(paths)):
            for right_index in range(left_index + 1, len(paths)):
                endpoint_match = closest_endpoint_pair(paths[left_index], paths[right_index])
                if endpoint_match[1] > snap_distance:
                    continue
                if best_pair is None or endpoint_match[1] < best_pair[3]:
                    best_pair = (left_index, right_index, endpoint_match[0], endpoint_match[1])
        if best_pair is None:
            continue
        left_index, right_index, endpoints, _ = best_pair
        merged_path = merge_pair(paths[left_index], paths[right_index], endpoints)
        paths[left_index] = merged_path
        paths.pop(right_index)
        changed = True
    return [simplify_path(path) for path in paths if path.total_length() >= MIN_SEGMENT_SPAN]


def closest_endpoint_pair(left: PolyPath, right: PolyPath) -> tuple[tuple[bool, bool], float]:
    pairs = [
        ((True, True), float(np.linalg.norm(left.start - right.start))),
        ((True, False), float(np.linalg.norm(left.start - right.end))),
        ((False, True), float(np.linalg.norm(left.end - right.start))),
        ((False, False), float(np.linalg.norm(left.end - right.end))),
    ]
    return min(pairs, key=lambda item: item[1])


def merge_pair(left: PolyPath, right: PolyPath, endpoints: tuple[bool, bool]) -> PolyPath:
    left_start, right_start = endpoints
    left_points = [point.copy() for point in (left.points if not left_start else list(reversed(left.points)))]
    right_points = [point.copy() for point in (right.points if right_start else list(reversed(right.points)))]

    junction = (left_points[-1] + right_points[0]) / 2.0
    left_points[-1] = junction
    right_points[0] = junction

    points = dedupe_points(left_points + right_points[1:])
    return PolyPath(points)


def merge_collinear_paths(paths: list[PolyPath], join_distance: float, angle_deg: float) -> list[PolyPath]:
    working = [path.copy() for path in paths]
    changed = True
    while changed and len(working) > 1:
        changed = False
        for left_index in range(len(working)):
            if changed:
                break
            for right_index in range(left_index + 1, len(working)):
                endpoints, distance = closest_endpoint_pair(working[left_index], working[right_index])
                if distance > join_distance:
                    continue
                candidate = merge_pair(working[left_index], working[right_index], endpoints)
                if turning_angle(candidate) < 180.0 - angle_deg:
                    continue
                working[left_index] = fit_straight_line(candidate.points)
                working.pop(right_index)
                changed = True
                break
    return [simplify_path(path) for path in working]


def turning_angle(path: PolyPath) -> float:
    if len(path.points) < 3:
        return 180.0
    first = path.points[1] - path.points[0]
    last = path.points[-2] - path.points[-1]
    return angle_between(first, last)


def fit_straight_line(points: list[np.ndarray]) -> PolyPath:
    array = np.stack(points, axis=0)
    center = array.mean(axis=0)
    _, _, vh = np.linalg.svd(array - center, full_matrices=False)
    direction = vh[0]
    projections = (array - center) @ direction
    start = center + direction * projections.min()
    end = center + direction * projections.max()
    ordered = [start.astype(np.float32), end.astype(np.float32)]
    return PolyPath(ordered)


def estimate_hub(paths: list[PolyPath], width: int, height: int) -> np.ndarray:
    usable = [path for path in paths if path.span() >= HUB_LINE_MIN_SPAN]
    if not usable:
        usable = paths

    matrix = np.zeros((2, 2), dtype=np.float64)
    vector = np.zeros(2, dtype=np.float64)
    for path in usable:
        start = path.start.astype(np.float64)
        end = path.end.astype(np.float64)
        direction = end - start
        norm = np.linalg.norm(direction)
        if norm <= 1e-6:
            continue
        normal = np.array([direction[1], -direction[0]], dtype=np.float64) / norm
        weight = max(path.span(), 1.0)
        matrix += weight * np.outer(normal, normal)
        vector += weight * np.outer(normal, normal) @ start

    if np.linalg.det(matrix) <= 1e-6:
        all_points = np.stack([point for path in usable for point in path.points], axis=0)
        hub = np.median(all_points, axis=0)
    else:
        hub = np.linalg.solve(matrix, vector)

    hub[0] = float(np.clip(hub[0], 0, width - 1))
    hub[1] = float(np.clip(hub[1], 0, height - 1))
    return hub.astype(np.float32)


def build_radial_paths(paths: list[PolyPath], hub: np.ndarray) -> list[PolyPath]:
    candidates: list[tuple[float, PolyPath]] = []
    for path in paths:
        if path.total_length() < MIN_SEGMENT_SPAN:
            continue
        farthest = max(path.points, key=lambda point: float(np.linalg.norm(point - hub)))
        angle = math.degrees(math.atan2(float(farthest[1] - hub[1]), float(farthest[0] - hub[0])))
        candidates.append((angle, path))

    candidates.sort(key=lambda item: item[0])
    clusters: list[list[PolyPath]] = []
    current: list[PolyPath] = []
    last_angle: float | None = None
    for angle, path in candidates:
        if last_angle is None or abs(angle - last_angle) <= RADIAL_CLUSTER_DEG:
            current.append(path)
        else:
            clusters.append(current)
            current = [path]
        last_angle = angle
    if current:
        clusters.append(current)

    refined: list[PolyPath] = []
    for cluster in clusters:
        all_points = np.stack([point for path in cluster for point in path.points], axis=0)
        centered = all_points - hub
        if np.allclose(centered, 0.0):
            continue
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        direction = vh[0]
        if np.dot(direction, centered.mean(axis=0)) < 0:
            direction = -direction
        projections = centered @ direction
        max_projection = float(projections.max())
        if max_projection < MIN_BRANCH_SPAN:
            continue
        outer = hub + direction * max_projection
        branch = PolyPath([outer.astype(np.float32), hub.astype(np.float32)])
        branch = simplify_path(branch)
        refined.append(branch)

    refined.sort(key=lambda item: item.start[1])
    return refined


def simplify_path(path: PolyPath) -> PolyPath:
    simplified = rdp(path.points, RDP_EPSILON)
    deduped = dedupe_points(simplified)
    return PolyPath(deduped)


def rdp(points: list[np.ndarray], epsilon: float) -> list[np.ndarray]:
    if len(points) < 3:
        return [point.copy() for point in points]

    start = points[0]
    end = points[-1]
    line = end - start
    line_norm = float(np.linalg.norm(line))
    if line_norm <= 1e-6:
        return [start.copy(), end.copy()]

    distances = []
    for point in points[1:-1]:
        offset = point - start
        cross = abs(line[0] * offset[1] - line[1] * offset[0])
        distances.append(float(cross / line_norm))

    if not distances:
        return [start.copy(), end.copy()]

    max_distance = max(distances)
    max_index = distances.index(max_distance) + 1
    if max_distance <= epsilon:
        return [start.copy(), end.copy()]

    left = rdp(points[: max_index + 1], epsilon)
    right = rdp(points[max_index:], epsilon)
    return left[:-1] + right


def dedupe_points(points: list[np.ndarray]) -> list[np.ndarray]:
    deduped: list[np.ndarray] = []
    for point in points:
        if not deduped or float(np.linalg.norm(point - deduped[-1])) > 1e-6:
            deduped.append(point.copy())
    return deduped


def angle_between(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-6 or right_norm <= 1e-6:
        return 0.0
    cosine = float(np.dot(left, right) / (left_norm * right_norm))
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def render_debug(image: np.ndarray, paths: list[PolyPath], hub: np.ndarray, output_path: Path) -> None:
    overlay = image.copy()
    rng = random.Random(23)
    for index, path in enumerate(paths):
        color = (rng.randint(40, 255), rng.randint(40, 255), rng.randint(40, 255))
        points = [(int(round(point[0])), int(round(point[1]))) for point in path.points]
        for left, right in zip(points, points[1:]):
            cv2.line(overlay, left, right, color, 2, cv2.LINE_AA)
        cv2.putText(
            overlay,
            str(index),
            points[0],
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )
    cv2.circle(overlay, (int(round(hub[0])), int(round(hub[1]))), 4, (0, 0, 255), -1)
    cv2.imwrite(str(output_path), overlay)


def write_svg(paths: list[PolyPath], width: int, height: int, output_path: Path) -> None:
    lines = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
        "<rect width='100%' height='100%' fill='#ffffff' />",
    ]
    for index, path in enumerate(paths):
        commands = []
        for point_index, point in enumerate(path.points):
            prefix = "M" if point_index == 0 else "L"
            commands.append(f"{prefix}{point[0]:.2f},{point[1]:.2f}")
        d = " ".join(commands)
        lines.append(
            f"<path id='refined-{index:03d}' d='{d}' fill='none' stroke='#374151' stroke-width='{SVG_STROKE_WIDTH}' stroke-linecap='round' stroke-linejoin='round' />"
        )
    lines.append("</svg>")
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
