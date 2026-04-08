from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

# Input / output configuration
INPUT_CANDIDATES = ("slice_B_icon.png", "B.png")
DEBUG_HIERARCHY_PATH = "debug_05_hierarchy.png"
OUTPUT_SVG_PATH = "slice_B_vector.svg"

# Core extraction parameters
THRESHOLD_MODE = "hybrid"  # one of: otsu, adaptive, hybrid
GAUSSIAN_BLUR_SIZE = 3
ADAPTIVE_BLOCK_SIZE = 31
ADAPTIVE_C = 7
MORPH_CLOSE_KERNEL = 3
MORPH_OPEN_KERNEL = 0
MIN_CONTOUR_AREA = 18.0
MIN_ROOT_AREA = 45.0
POLY_EPSILON_RATIO = 0.012
MAX_ROOTS = 12
ROOT_SCORE_RELATIVE_MIN = 0.18
SHORT_EDGE_THRESHOLD = 3.0
COLLINEAR_SINE_THRESHOLD = 0.08

# Visual debug colors (BGR)
OUTER_COLOR = (0, 200, 0)
HOLE_COLOR = (0, 0, 220)


@dataclass(slots=True)
class ContourNode:
    index: int
    depth: int
    area: float
    bbox: tuple[int, int, int, int]


def resolve_input_path(base_dir: Path) -> Path:
    for name in INPUT_CANDIDATES:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No input image found in {base_dir}; tried: {INPUT_CANDIDATES}")


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def preprocess_mask(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_size = max(1, ensure_odd(GAUSSIAN_BLUR_SIZE))
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0) if blur_size > 1 else gray.copy()

    _, otsu_mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    adaptive_mask = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        ensure_odd(max(3, ADAPTIVE_BLOCK_SIZE)),
        ADAPTIVE_C,
    )

    if THRESHOLD_MODE == "otsu":
        mask = otsu_mask
    elif THRESHOLD_MODE == "adaptive":
        mask = adaptive_mask
    else:
        mask = cv2.bitwise_or(otsu_mask, adaptive_mask)

    if MORPH_CLOSE_KERNEL > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (ensure_odd(MORPH_CLOSE_KERNEL), ensure_odd(MORPH_CLOSE_KERNEL)),
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    if MORPH_OPEN_KERNEL > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (ensure_odd(MORPH_OPEN_KERNEL), ensure_odd(MORPH_OPEN_KERNEL)),
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    return gray, mask


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    depth = 0
    parent = hierarchy[index][3]
    while parent != -1:
        depth += 1
        parent = hierarchy[parent][3]
    return depth


def subtree_indices(root_index: int, hierarchy: np.ndarray) -> list[int]:
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


def root_score(root_index: int, contours: list[np.ndarray], hierarchy: np.ndarray, image_shape: tuple[int, int]) -> float:
    root = contours[root_index]
    area = cv2.contourArea(root)
    x, y, w, h = cv2.boundingRect(root)
    image_h, image_w = image_shape
    cx = x + (w / 2.0)
    cy = y + (h / 2.0)
    distance_from_center = ((cx - image_w / 2.0) ** 2 + (cy - image_h / 2.0) ** 2) ** 0.5
    max_distance = max((image_w**2 + image_h**2) ** 0.5 / 2.0, 1.0)
    center_bonus = 1.0 - min(distance_from_center / max_distance, 1.0)
    descendants = subtree_indices(root_index, hierarchy)
    child_bonus = max(len(descendants) - 1, 0) * 12.0
    return area + child_bonus + center_bonus * 25.0


def select_root_indices(contours: list[np.ndarray], hierarchy: np.ndarray, image_shape: tuple[int, int]) -> list[int]:
    roots: list[tuple[float, int]] = []
    for index, contour in enumerate(contours):
        if hierarchy[index][3] != -1:
            continue
        area = cv2.contourArea(contour)
        if area < MIN_ROOT_AREA:
            continue
        roots.append((root_score(index, contours, hierarchy, image_shape), index))

    roots.sort(reverse=True)
    if not roots:
        return []

    best_score = roots[0][0]
    filtered = [
        index
        for score, index in roots[:MAX_ROOTS]
        if score >= best_score * ROOT_SCORE_RELATIVE_MIN
    ]
    return filtered or [roots[0][1]]


def approximate_contour(contour: np.ndarray) -> np.ndarray:
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(1.0, perimeter * POLY_EPSILON_RATIO)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = approx.reshape(-1, 2) if len(approx) >= 3 else contour.reshape(-1, 2)
    return smooth_closed_polygon(points)


def smooth_closed_polygon(points: np.ndarray) -> np.ndarray:
    cleaned = _dedupe_points(points)
    if len(cleaned) <= 3:
        return cleaned

    changed = True
    current = cleaned
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

            if min(prev_len, next_len) <= SHORT_EDGE_THRESHOLD:
                changed = True
                continue

            sin_theta = abs(_cross_2d(prev_vec, next_vec)) / max(prev_len * next_len, 1e-6)
            dot = float(np.dot(prev_vec, next_vec))
            if dot > 0.0 and sin_theta <= COLLINEAR_SINE_THRESHOLD:
                changed = True
                continue

            next_points.append(point)

        if len(next_points) < 3:
            break
        current = np.asarray(next_points, dtype=np.int32)

    return current


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


def contour_to_svg_path(points: np.ndarray) -> str:
    coords = [f"{int(x)},{int(y)}" for x, y in points]
    if not coords:
        return ""
    return "M " + " L ".join(coords) + " Z"


def build_svg_path(contours: list[np.ndarray], hierarchy: np.ndarray, root_indices: Iterable[int]) -> tuple[str, list[ContourNode]]:
    fragments: list[str] = []
    nodes: list[ContourNode] = []
    selected = set()
    for root_index in root_indices:
        for index in subtree_indices(root_index, hierarchy):
            if index in selected:
                continue
            selected.add(index)
            contour = contours[index]
            area = cv2.contourArea(contour)
            if area < MIN_CONTOUR_AREA:
                continue
            approx = approximate_contour(contour)
            path_fragment = contour_to_svg_path(approx)
            if not path_fragment:
                continue
            fragments.append(path_fragment)
            x, y, w, h = cv2.boundingRect(contour)
            nodes.append(ContourNode(index=index, depth=contour_depth(index, hierarchy), area=area, bbox=(x, y, w, h)))
    return " ".join(fragments), nodes


def draw_hierarchy_debug(image: np.ndarray, contours: list[np.ndarray], nodes: Iterable[ContourNode]) -> np.ndarray:
    canvas = image.copy()
    for node in sorted(nodes, key=lambda item: item.depth):
        color = OUTER_COLOR if node.depth % 2 == 0 else HOLE_COLOR
        cv2.drawContours(canvas, contours, node.index, color, 2, cv2.LINE_AA)
    return canvas


def write_svg(path: Path, width: int, height: int, compound_path: str) -> None:
    svg = "\n".join(
        [
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
            "  <rect width='100%' height='100%' fill='#ffffff' />",
            f"  <path d='{compound_path}' fill='#111111' fill-rule='evenodd' stroke='none' />",
            "</svg>",
        ]
    )
    path.write_text(svg, encoding='utf-8')


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    input_path = resolve_input_path(base_dir)
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Failed to load image: {input_path}")

    gray, mask = preprocess_mask(image)
    contours, raw_hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if raw_hierarchy is None or not contours:
        raise RuntimeError("No contours found from RETR_TREE pass")
    hierarchy = raw_hierarchy[0]

    root_indices = select_root_indices(contours, hierarchy, gray.shape)
    if not root_indices:
        raise RuntimeError("No valid root contours selected")

    compound_path, nodes = build_svg_path(contours, hierarchy, root_indices)
    if not compound_path:
        raise RuntimeError("Selected contour tree did not yield any SVG path data")

    debug_image = draw_hierarchy_debug(image, contours, nodes)
    debug_path = base_dir / DEBUG_HIERARCHY_PATH
    svg_path = base_dir / OUTPUT_SVG_PATH
    cv2.imwrite(str(debug_path), debug_image)
    write_svg(svg_path, image.shape[1], image.shape[0], compound_path)

    print(f"input={input_path}")
    print(f"roots={len(root_indices)} selected_contours={len(nodes)}")
    print(f"debug={debug_path}")
    print(f"svg={svg_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
