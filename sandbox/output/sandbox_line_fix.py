from __future__ import annotations

from pathlib import Path
import math

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
INPUT_CANDIDATES = [
    BASE_DIR / "A.png",
    BASE_DIR.parent / "A.png",
]
SKELETON_PATH = BASE_DIR / "debug_A_skeleton.png"
LINES_PATH = BASE_DIR / "debug_A_lines.png"
MERGED_LINES_PATH = BASE_DIR / "debug_A_merged_lines.png"
RAW_SVG_PATH = BASE_DIR / "debug_A_lines.svg"
MERGED_SVG_PATH = BASE_DIR / "debug_A_merged_lines.svg"
ANGLE_TOLERANCE = 2.0
RHO_TOLERANCE = 12.0
MERGE_DISTANCE = 30.0
RADIAL_ANGLE_TOLERANCE = 6.0
MAX_RADIAL_LINES = 10
MIN_OUTPUT_LENGTH = 85.0


def resolve_input_path() -> Path:
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("A.png not found in sandbox/output or sandbox root")


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def adaptive_binary(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)


def thin_mask(binary: np.ndarray) -> np.ndarray:
    if not hasattr(cv2, "ximgproc") or not hasattr(cv2.ximgproc, "thinning"):
        raise RuntimeError("cv2.ximgproc.thinning is required but unavailable in this environment")
    return cv2.ximgproc.thinning(binary)


def normalize_line(line: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = line
    if (x1, y1) <= (x2, y2):
        return line
    return (x2, y2, x1, y1)


def line_angle(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def line_orientation(line: tuple[int, int, int, int]) -> float:
    return line_angle(line) % 180.0


def angular_gap(left: float, right: float, period: float = 180.0) -> float:
    gap = abs(left - right) % period
    return min(gap, period - gap)


def line_length(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    return math.hypot(x2 - x1, y2 - y1)


def line_rho(line: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = line
    theta = math.atan2(y2 - y1, x2 - x1) + math.pi / 2.0
    return x1 * math.cos(theta) + y1 * math.sin(theta)


def point_line_distance(point: tuple[int, int], line: tuple[int, int, int, int]) -> float:
    x0, y0 = point
    x1, y1, x2, y2 = line
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def endpoint_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    left_points = [(left[0], left[1]), (left[2], left[3])]
    right_points = [(right[0], right[1]), (right[2], right[3])]
    return min(math.hypot(ax - bx, ay - by) for ax, ay in left_points for bx, by in right_points)


def projection_interval(line: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = line
    direction = np.array([x2 - x1, y2 - y1], dtype=np.float32)
    length = float(np.hypot(direction[0], direction[1]))
    if length == 0.0:
        return 0.0, 0.0
    direction /= length
    p1 = float(direction[0] * x1 + direction[1] * y1)
    p2 = float(direction[0] * x2 + direction[1] * y2)
    return min(p1, p2), max(p1, p2)


def interval_gap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    left_min, left_max = projection_interval(left)
    right_min, right_max = projection_interval(right)
    if left_max < right_min:
        return right_min - left_max
    if right_max < left_min:
        return left_min - right_max
    return 0.0


def dedupe_lines(lines: list[tuple[int, int, int, int]], tolerance: int = 3) -> list[tuple[int, int, int, int]]:
    unique: list[tuple[int, int, int, int]] = []
    for line in lines:
        candidate = normalize_line(line)
        if any(max(abs(a - b) for a, b in zip(candidate, existing)) <= tolerance for existing in unique):
            continue
        unique.append(candidate)
    return unique


def detect_hough_lines(skeleton: np.ndarray) -> list[tuple[int, int, int, int]]:
    raw_lines = cv2.HoughLinesP(
        skeleton,
        rho=1,
        theta=np.pi / 180,
        threshold=18,
        minLineLength=35,
        maxLineGap=22,
    )
    if raw_lines is None:
        return []
    candidates: list[tuple[int, int, int, int]] = []
    for raw in raw_lines[:, 0, :]:
        candidate = normalize_line(tuple(map(int, raw.tolist())))
        if line_length(candidate) < 35.0:
            continue
        candidates.append(candidate)
    return candidates


def detect_lsd_lines(skeleton: np.ndarray) -> list[tuple[int, int, int, int]]:
    if not hasattr(cv2, "createLineSegmentDetector"):
        return []
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    detected = detector.detect(skeleton)[0]
    if detected is None:
        return []
    candidates: list[tuple[int, int, int, int]] = []
    for raw in detected[:, 0, :]:
        candidate = normalize_line(tuple(int(round(value)) for value in raw.tolist()))
        if line_length(candidate) < 25.0:
            continue
        candidates.append(candidate)
    return candidates


def detect_lines(skeleton: np.ndarray) -> list[tuple[int, int, int, int]]:
    candidates = detect_hough_lines(skeleton)
    candidates.extend(detect_lsd_lines(skeleton))
    return dedupe_lines(candidates)


def detect_source_nodes(image: np.ndarray) -> list[tuple[int, int, int]]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (90, 60, 40), (130, 255, 255))
    components, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    circles: list[tuple[int, int, int]] = []
    width = image.shape[1]
    for index in range(1, components):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < 180 or area > 320:
            continue
        x, y, w, h = stats[index, :4]
        if x > width * 0.45:
            continue
        cx, cy = centroids[index]
        radius = int(round(max(w, h) / 2.0))
        circles.append((int(round(cx)), int(round(cy)), radius))
    circles.sort(key=lambda item: item[1])
    return circles


def detect_target_hub(image: np.ndarray) -> tuple[int, int, int]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=14,
        param1=100,
        param2=14,
        minRadius=5,
        maxRadius=12,
    )
    if circles is not None:
        width = image.shape[1]
        height = image.shape[0]
        candidates = []
        for cx, cy, radius in np.round(circles[0]).astype(int):
            if cx <= width * 0.6:
                continue
            if not (height * 0.35 <= cy <= height * 0.65):
                continue
            candidates.append((cx, cy, int(radius)))
        if candidates:
            candidates.sort(key=lambda item: (item[0], -item[2]), reverse=True)
            return candidates[0]
    return (115, image.shape[0] // 2, 10)


def cluster_by_orientation(
    lines: list[tuple[int, int, int, int]],
    angle_tolerance: float = ANGLE_TOLERANCE,
) -> list[list[tuple[int, int, int, int]]]:
    if not lines:
        return []
    sorted_lines = sorted(lines, key=line_orientation)
    clusters: list[list[tuple[int, int, int, int]]] = []
    current = [sorted_lines[0]]
    current_center = line_orientation(sorted_lines[0])
    for line in sorted_lines[1:]:
        orientation = line_orientation(line)
        if angular_gap(orientation, current_center) <= angle_tolerance:
            current.append(line)
            current_center = sum(line_orientation(item) for item in current) / len(current)
        else:
            clusters.append(current)
            current = [line]
            current_center = orientation
    clusters.append(current)
    return clusters


def can_merge_lines(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    if angular_gap(line_orientation(left), line_orientation(right)) > ANGLE_TOLERANCE:
        return False
    if abs(line_rho(left) - line_rho(right)) > RHO_TOLERANCE:
        return False
    distances = [
        point_line_distance((left[0], left[1]), right),
        point_line_distance((left[2], left[3]), right),
        point_line_distance((right[0], right[1]), left),
        point_line_distance((right[2], right[3]), left),
    ]
    if max(distances) > 8.0:
        return False
    return endpoint_gap(left, right) <= MERGE_DISTANCE or interval_gap(left, right) <= MERGE_DISTANCE


def merge_pair(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
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
    return normalize_line(tuple(int(round(value)) for value in [start[0], start[1], end[0], end[1]]))


def merge_orientation_clusters(lines: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for cluster in cluster_by_orientation(lines):
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
                    if can_merge_lines(candidate, remaining[follow]):
                        candidate = merge_pair(candidate, remaining[follow])
                        used[follow] = True
                        changed = True
                used[index] = True
                next_lines.append(candidate)
            remaining = next_lines
        merged.extend(remaining)
    merged.sort(key=line_length, reverse=True)
    return dedupe_lines(merged, tolerance=2)


def line_intersection(
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


def estimate_hub(lines: list[tuple[int, int, int, int]]) -> tuple[float, float]:
    intersections: list[tuple[float, float]] = []
    for index, left in enumerate(lines):
        for right in lines[index + 1 :]:
            if angular_gap(line_orientation(left), line_orientation(right)) < 8.0:
                continue
            point = line_intersection(left, right)
            if point is None:
                continue
            px, py = point
            if -50.0 <= px <= 200.0 and 0.0 <= py <= 450.0:
                intersections.append(point)
    if not intersections:
        rightmost = max(lines, key=lambda item: max(item[0], item[2]))
        return float(max(rightmost[0], rightmost[2])), float((rightmost[1] + rightmost[3]) / 2.0)
    best = max(
        intersections,
        key=lambda point: sum(
            (point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2 <= 20.0 ** 2
            for other in intersections
        ),
    )
    return best


def far_endpoint(line: tuple[int, int, int, int], hub: tuple[float, float]) -> tuple[tuple[int, int], float]:
    points = [(line[0], line[1]), (line[2], line[3])]
    distances = [math.hypot(px - hub[0], py - hub[1]) for px, py in points]
    index = 0 if distances[0] >= distances[1] else 1
    return points[index], distances[index]


def cluster_radial_lines(
    lines: list[tuple[int, int, int, int]],
    hub: tuple[float, float],
) -> list[tuple[int, int, int, int]]:
    items = []
    for line in lines:
        far_point, far_distance = far_endpoint(line, hub)
        if far_distance < 60.0:
            continue
        angle = (math.degrees(math.atan2(far_point[1] - hub[1], far_point[0] - hub[0])) + 360.0) % 360.0
        items.append(
            {
                "angle": angle,
                "distance": far_distance,
                "point": far_point,
                "line": line,
            }
        )
    if not items:
        return lines
    items.sort(key=lambda item: item["angle"])
    clusters: list[list[dict[str, object]]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            center = sum(float(entry["angle"]) for entry in cluster) / len(cluster)
            if abs(float(item["angle"]) - center) <= RADIAL_ANGLE_TOLERANCE:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    while len(clusters) > MAX_RADIAL_LINES:
        best_index = 0
        best_gap = float("inf")
        for index in range(len(clusters) - 1):
            left = sum(float(entry["angle"]) for entry in clusters[index]) / len(clusters[index])
            right = sum(float(entry["angle"]) for entry in clusters[index + 1]) / len(clusters[index + 1])
            gap = right - left
            if gap < best_gap:
                best_gap = gap
                best_index = index
        clusters[best_index].extend(clusters[best_index + 1])
        clusters.pop(best_index + 1)

    radial_lines: list[tuple[int, int, int, int]] = []
    hub_point = (int(round(hub[0])), int(round(hub[1])))
    for cluster in clusters:
        representative = max(cluster, key=lambda entry: float(entry["distance"]))
        if float(representative["distance"]) < MIN_OUTPUT_LENGTH:
            continue
        far_point = representative["point"]
        radial_lines.append(normalize_line((hub_point[0], hub_point[1], int(far_point[0]), int(far_point[1]))))
    radial_lines.sort(key=lambda line: ((math.degrees(math.atan2(line[3] - hub[1], line[2] - hub[0])) + 360.0) % 360.0))
    return dedupe_lines(radial_lines, tolerance=2)


def merge_lines(lines: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged_candidates = merge_orientation_clusters(lines)
    hub = estimate_hub(merged_candidates or lines)
    return cluster_radial_lines(merged_candidates or lines, hub)


def line_support(
    skeleton: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
) -> int:
    mask = np.zeros_like(skeleton)
    cv2.line(mask, start, end, 255, 2, cv2.LINE_AA)
    return int(np.count_nonzero(cv2.bitwise_and(skeleton, mask)))


def build_node_driven_lines(
    nodes: list[tuple[int, int, int]],
    hub: tuple[int, int, int],
    skeleton: np.ndarray,
) -> list[tuple[int, int, int, int]]:
    hub_point = np.array([hub[0], hub[1]], dtype=np.float32)
    hub_radius = float(hub[2])
    lines: list[tuple[int, int, int, int]] = []
    for cx, cy, radius in nodes:
        source = np.array([cx, cy], dtype=np.float32)
        vector = hub_point - source
        length = float(np.hypot(vector[0], vector[1]))
        if length == 0.0:
            continue
        unit = vector / length
        start = source + unit * max(radius - 1.0, 1.0)
        end = hub_point - unit * max(hub_radius * 0.6, 2.0)
        start_point = (int(round(start[0])), int(round(start[1])))
        end_point = (int(round(end[0])), int(round(end[1])))
        if line_support(skeleton, start_point, end_point) < 12:
            continue
        lines.append(normalize_line((start_point[0], start_point[1], end_point[0], end_point[1])))
    return dedupe_lines(lines, tolerance=1)


def reconstruct_lines(image: np.ndarray, skeleton: np.ndarray) -> tuple[
    list[tuple[int, int, int, int]],
    list[tuple[int, int, int, int]],
    tuple[float, float],
]:
    raw_lines = detect_lines(skeleton)
    nodes = detect_source_nodes(image)
    hub_circle = detect_target_hub(image)
    final_lines = build_node_driven_lines(nodes, hub_circle, skeleton)
    if not final_lines:
        merged_candidates = merge_orientation_clusters(raw_lines)
        fallback_hub = estimate_hub(merged_candidates or raw_lines)
        final_lines = cluster_radial_lines(merged_candidates or raw_lines, fallback_hub)
        return raw_lines, final_lines, fallback_hub
    return raw_lines, final_lines, (float(hub_circle[0]), float(hub_circle[1]))


def save_debug_images(
    image: np.ndarray,
    skeleton: np.ndarray,
    raw_lines: list[tuple[int, int, int, int]],
    merged_lines: list[tuple[int, int, int, int]],
    hub: tuple[float, float],
) -> None:
    cv2.imwrite(str(SKELETON_PATH), skeleton)
    raw_overlay = image.copy()
    for x1, y1, x2, y2 in raw_lines:
        cv2.line(raw_overlay, (x1, y1), (x2, y2), (0, 0, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(LINES_PATH), raw_overlay)

    merged_overlay = image.copy()
    palette = [
        (255, 0, 0),
        (0, 180, 0),
        (0, 0, 255),
        (255, 128, 0),
        (180, 0, 180),
        (0, 180, 180),
        (120, 60, 255),
        (60, 220, 120),
        (255, 60, 120),
        (40, 140, 255),
    ]
    for index, (x1, y1, x2, y2) in enumerate(merged_lines):
        color = palette[index % len(palette)]
        cv2.line(merged_overlay, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        cv2.putText(
            merged_overlay,
            str(index + 1),
            (x2 + 2, y2 - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            color,
            1,
            cv2.LINE_AA,
        )
    cv2.circle(merged_overlay, (int(round(hub[0])), int(round(hub[1]))), 4, (0, 0, 0), -1, cv2.LINE_AA)
    cv2.imwrite(str(MERGED_LINES_PATH), merged_overlay)


def export_svg(
    path: Path,
    width: int,
    height: int,
    lines: list[tuple[int, int, int, int]],
    stroke: str,
) -> str:
    body = []
    for index, (x1, y1, x2, y2) in enumerate(lines, start=1):
        body.append(
            f"  <line id='line-{index:03d}' x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' "
            f"stroke='{stroke}' stroke-width='2' stroke-linecap='round' />"
        )
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}'>\n"
        "  <rect width='100%' height='100%' fill='#f5f5f5' />\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")
    return svg


def main() -> None:
    input_path = resolve_input_path()
    image = load_image(input_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = adaptive_binary(gray)
    skeleton = thin_mask(binary)
    raw_lines, merged_lines, hub = reconstruct_lines(image, skeleton)
    save_debug_images(image, skeleton, raw_lines, merged_lines, hub)
    export_svg(RAW_SVG_PATH, image.shape[1], image.shape[0], raw_lines, "#999999")
    merged_svg = export_svg(MERGED_SVG_PATH, image.shape[1], image.shape[0], merged_lines, "#d60000")
    print(f"input={input_path.name}")
    print(f"skeleton_pixels={int(np.count_nonzero(skeleton))}")
    print(f"raw_line_count={len(raw_lines)}")
    print(f"merged_line_count={len(merged_lines)}")
    print(f"hub=({hub[0]:.2f}, {hub[1]:.2f})")
    print(f"merged_debug_path={MERGED_LINES_PATH}")
    print(f"merged_svg_path={MERGED_SVG_PATH}")
    for index, line in enumerate(merged_lines, start=1):
        print(f"merged_line_{index}: {line} length={line_length(line):.1f}")
    print(merged_svg)


if __name__ == "__main__":
    main()
