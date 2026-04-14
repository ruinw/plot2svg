"""Object-driven stroke detection and polyline tracing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import PipelineConfig, ThresholdConfig
from .image_io import read_image, write_image

from .dense_line_reconstructor import line_length as dense_line_length
from .dense_line_reconstructor import reconstruct_dense_lines, render_line_mask
from .scene_graph import SceneGraph, SceneNode, StrokePrimitive


@dataclass(slots=True)
class _TracedPrimitive:
    points: list[list[float]]
    width: float
    arrow_head: dict[str, object] | None
    metadata: dict[str, object]
    id_suffix: str = ''


def detect_strokes(
    image_input: Path | np.ndarray,
    scene_graph: SceneGraph,
    coordinate_scale: float = 1.0,
    cfg: PipelineConfig | None = None,
    debug_mask_path: Path | None = None,
) -> list[StrokePrimitive]:
    """Trace scene-graph stroke nodes into editable polylines."""

    image = _load_gray_image(image_input)
    arrow_region_nodes = [
        node
        for node in scene_graph.nodes
        if node.type == 'region' and node.shape_hint == 'triangle'
    ]
    thresholds = _stroke_thresholds(cfg)
    primitives: list[StrokePrimitive] = []
    debug_mask = np.zeros((scene_graph.height, scene_graph.width), dtype=np.uint8)
    for node in scene_graph.nodes:
        if node.type != 'stroke':
            continue
        crop = _extract_scaled_crop(image, node.bbox, coordinate_scale)
        traced_primitives, local_mask = _trace_stroke_crop(crop, node.bbox, arrow_region_nodes, thresholds)
        _merge_debug_mask(debug_mask, local_mask, node.bbox)
        for traced in traced_primitives:
            if not _should_emit_stroke_primitive(
                traced.points,
                traced.width,
                scene_graph.width,
                scene_graph.height,
                thresholds=thresholds,
            ):
                continue
            primitive_id = f'stroke-primitive-{node.id}{traced.id_suffix}'
            primitives.append(
                StrokePrimitive(
                    id=primitive_id,
                    node_id=node.id,
                    points=traced.points,
                    width=traced.width,
                    arrow_head=traced.arrow_head,
                    metadata={'source': 'stroke_detector', **traced.metadata},
                )
            )
    if debug_mask_path is not None:
        debug_mask_path.parent.mkdir(parents=True, exist_ok=True)
        write_image(debug_mask_path, debug_mask)
    return primitives



def is_stroke_sane(
    stroke_points: list[list[float]],
    image_width: int,
    image_height: int,
    stroke_width: float,
    thresholds: ThresholdConfig | None = None,
) -> bool:
    """Reject globally implausible stroke hallucinations."""

    thresholds = thresholds or ThresholdConfig()
    if not stroke_points or len(stroke_points) < 2:
        return False

    xs = [point[0] for point in stroke_points]
    ys = [point[1] for point in stroke_points]
    bbox_w = max(xs) - min(xs)
    bbox_h = max(ys) - min(ys)
    if bbox_w > image_width * thresholds.stroke_sane_canvas_span_ratio or bbox_h > image_height * thresholds.stroke_sane_canvas_span_ratio:
        return False
    if stroke_width > thresholds.stroke_sane_max_width:
        return False
    return True


def _should_emit_stroke_primitive(
    points: list[list[float]],
    width: float,
    image_width: int,
    image_height: int,
    thresholds: ThresholdConfig | None = None,
) -> bool:
    thresholds = thresholds or ThresholdConfig()
    if _polyline_length(points) < thresholds.stroke_min_polyline_length:
        return False
    return is_stroke_sane(points, image_width, image_height, width, thresholds=thresholds)


def _polyline_length(points: list[list[float]]) -> float:
    length = 0.0
    for left, right in zip(points, points[1:]):
        length += ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
    return length


def _trace_stroke_crop(
    crop: np.ndarray,
    bbox: list[int],
    arrow_region_nodes: list[SceneNode],
    thresholds: ThresholdConfig,
) -> tuple[list[_TracedPrimitive], np.ndarray]:
    x1, y1, x2, y2 = bbox
    empty_mask = np.zeros((max(y2 - y1, 1), max(x2 - x1, 1)), dtype=np.uint8)
    if crop.size == 0:
        return [_fallback_traced_primitive(x1, y1, x2, y2)], empty_mask

    mask, detector_mode = _build_stroke_mask(crop)
    trace_mask = mask
    used_skeleton = False
    if _should_use_skeleton(mask):
        skeleton = _skeletonize_mask(mask)
        if np.count_nonzero(skeleton) >= 2:
            trace_mask = skeleton
            detector_mode = f'{detector_mode}+skeleton'
            used_skeleton = True

    dense_attempted = _should_reconstruct_dense_lines(mask, trace_mask, used_skeleton, thresholds=thresholds)
    dense_primitives = _trace_dense_line_cluster(mask, trace_mask, bbox, detector_mode, used_skeleton, thresholds)
    if dense_primitives is not None:
        return dense_primitives, render_line_mask(trace_mask.shape, [
            (
                int(round(primitive.points[0][0] - x1)),
                int(round(primitive.points[0][1] - y1)),
                int(round(primitive.points[-1][0] - x1)),
                int(round(primitive.points[-1][1] - y1)),
            )
            for primitive in dense_primitives
        ])
    if dense_attempted:
        used_skeleton = False

    trace_coords = np.column_stack(np.where(trace_mask > 0))
    mask_coords = np.column_stack(np.where(mask > 0))
    if len(trace_coords) < 2 or len(mask_coords) < 2:
        return [
            _TracedPrimitive(
                points=[[float(x1), float(y1)], [float(x2), float(y2)]],
                width=1.0,
                arrow_head=None,
                metadata={
                    'detector_mode': detector_mode,
                    'arrow_absorbed': False,
                    'used_skeleton': used_skeleton,
                    'absorbed_region_ids': [],
                    'dense_reconstruction': False,
                },
            )
        ], trace_mask

    if used_skeleton:
        points = _trace_mask_polyline(trace_mask, float(x1), float(y1))
    else:
        points = _principal_polyline(mask_coords, float(x1), float(y1))
    width = _estimate_width(mask, points)
    absorbed_arrow, endpoint_index = _absorb_endpoint_triangle(mask, points, bbox, width)
    absorbed_region_ids: list[str] = []
    region_arrow, region_endpoint, region_id = _anchor_arrow_to_region(points, width, arrow_region_nodes)
    if region_id is not None:
        absorbed_region_ids.append(region_id)
    if region_arrow is not None and region_endpoint is not None:
        points[region_endpoint] = region_arrow['tip'][:]
    elif absorbed_arrow is not None and endpoint_index is not None:
        points[endpoint_index] = absorbed_arrow['tip'][:]

    arrow_head = region_arrow or absorbed_arrow or _detect_arrow_head(mask_coords, points, width)
    arrow_head = _constrain_arrow_head(arrow_head, width)
    return [
        _TracedPrimitive(
            points=points,
            width=width,
            arrow_head=arrow_head,
            metadata={
                'detector_mode': detector_mode,
                'arrow_absorbed': bool(absorbed_arrow is not None or region_arrow is not None),
                'used_skeleton': used_skeleton,
                'absorbed_region_ids': absorbed_region_ids,
                'dense_reconstruction': False,
            },
        )
    ], trace_mask


def _fallback_traced_primitive(x1: int, y1: int, x2: int, y2: int) -> _TracedPrimitive:
    return _TracedPrimitive(
        points=[[float(x1), float(y1)], [float(x2), float(y2)]],
        width=1.0,
        arrow_head=None,
        metadata={
            'detector_mode': 'empty-fallback',
            'arrow_absorbed': False,
            'used_skeleton': False,
            'absorbed_region_ids': [],
            'dense_reconstruction': False,
        },
    )


def _trace_dense_line_cluster(
    mask: np.ndarray,
    trace_mask: np.ndarray,
    bbox: list[int],
    detector_mode: str,
    used_skeleton: bool,
    thresholds: ThresholdConfig,
) -> list[_TracedPrimitive] | None:
    if not _should_reconstruct_dense_lines(mask, trace_mask, used_skeleton, thresholds=thresholds):
        return None
    reconstruction = reconstruct_dense_lines(trace_mask)
    if reconstruction is None or len(reconstruction.lines) < 3:
        return None
    if _looks_like_false_dense_hub(mask, reconstruction.lines):
        return None

    x1, y1, _x2, _y2 = bbox
    total_length = sum(dense_line_length(line) for line in reconstruction.lines)
    width = max(float(np.count_nonzero(mask)) / max(total_length, 1.0), 1.0)
    primitives: list[_TracedPrimitive] = []
    for index, line in enumerate(reconstruction.lines, start=1):
        local_points = [
            [float(line[0] + x1), float(line[1] + y1)],
            [float(line[2] + x1), float(line[3] + y1)],
        ]
        primitives.append(
            _TracedPrimitive(
                points=local_points,
                width=width,
                arrow_head=None,
                metadata={
                    'detector_mode': f'{detector_mode}+dense-lines',
                    'arrow_absorbed': False,
                    'used_skeleton': used_skeleton,
                    'absorbed_region_ids': [],
                    'dense_reconstruction': True,
                    'dense_reconstruction_line_count': len(reconstruction.lines),
                    'dense_raw_line_count': reconstruction.raw_count,
                    'dense_merged_line_count': reconstruction.merged_count,
                    'dense_hub': [round(reconstruction.hub[0], 2), round(reconstruction.hub[1], 2)],
                },
                id_suffix=f'-{index:02d}',
            )
        )
    return primitives


def _looks_like_false_dense_hub(mask: np.ndarray, lines: list[tuple[int, int, int, int]]) -> bool:
    if len(lines) < 5:
        return False
    coords = np.column_stack(np.where(mask > 0))
    if len(coords) < 2:
        return False
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    width = int(x2 - x1 + 1)
    height = int(y2 - y1 + 1)
    aspect_ratio = max(width, 1) / max(height, 1)
    if aspect_ratio < 4.0:
        return False
    lengths = [dense_line_length(line) for line in lines]
    if not lengths:
        return False
    longest = max(lengths)
    short_count = sum(length < longest * 0.5 for length in lengths)
    return short_count >= len(lines) - 2


def _should_reconstruct_dense_lines(
    mask: np.ndarray,
    trace_mask: np.ndarray,
    used_skeleton: bool,
    thresholds: ThresholdConfig | None = None,
) -> bool:
    thresholds = thresholds or ThresholdConfig()
    if not used_skeleton:
        return False
    mask_coords = np.column_stack(np.where(mask > 0))
    trace_coords = np.column_stack(np.where(trace_mask > 0))
    if len(mask_coords) < thresholds.stroke_dense_min_mask_pixels or len(trace_coords) < thresholds.stroke_dense_min_trace_pixels:
        return False
    y1, x1 = mask_coords.min(axis=0)
    y2, x2 = mask_coords.max(axis=0)
    width = int(x2 - x1 + 1)
    height = int(y2 - y1 + 1)
    if width < thresholds.stroke_dense_min_width or height < thresholds.stroke_dense_min_height:
        return False
    if width * height > thresholds.stroke_dense_max_area:
        return False
    if len(mask_coords) > thresholds.stroke_dense_max_mask_pixels or len(trace_coords) > thresholds.stroke_dense_max_trace_pixels:
        return False
    fill_ratio = float(len(mask_coords)) / max(float(width * height), 1.0)
    aspect_ratio = max(width, 1) / max(height, 1)
    if aspect_ratio >= 4.0 and fill_ratio <= 0.18:
        return False
    return fill_ratio >= thresholds.stroke_dense_min_fill_ratio


def _stroke_thresholds(cfg: PipelineConfig | None) -> ThresholdConfig:
    if cfg is not None and cfg.thresholds is not None:
        return cfg.thresholds
    return ThresholdConfig()


def _build_stroke_mask(crop: np.ndarray) -> tuple[np.ndarray, str]:
    prepared = _prepare_stroke_crop(crop)
    if prepared.size == 0:
        return prepared, 'empty-crop'
    if min(prepared.shape[:2]) < 2:
        return np.zeros_like(prepared), 'tiny-crop'

    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        clahe_enhanced = clahe.apply(prepared)
        blurred = cv2.GaussianBlur(clahe_enhanced, (3, 3), 0)
        _, otsu_mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        background = cv2.GaussianBlur(blurred, (21, 21), 0)
        contrast = cv2.subtract(background, blurred)
        contrast_threshold = max(int(np.mean(contrast) + np.std(contrast) * 0.45), 5)
        _, contrast_mask = cv2.threshold(contrast, contrast_threshold, 255, cv2.THRESH_BINARY)

        blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, np.ones((9, 9), np.uint8))
        blackhat_threshold = max(int(np.mean(blackhat) + np.std(blackhat) * 0.30), 3)
        _, blackhat_mask = cv2.threshold(blackhat, blackhat_threshold, 255, cv2.THRESH_BINARY)

        adaptive_mask = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            3,
        )
    except cv2.error:
        return np.zeros_like(prepared), 'opencv-fallback-empty'

    combined = cv2.bitwise_or(adaptive_mask, contrast_mask)
    combined = cv2.bitwise_or(combined, blackhat_mask)
    if np.count_nonzero(combined) < 24:
        combined = cv2.bitwise_or(combined, otsu_mask)
        detector_mode = 'clahe+adaptive+contrast+blackhat+otsu'
    else:
        detector_mode = 'clahe+adaptive+contrast+blackhat'

    kernel = np.ones((2, 2), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    return _filter_stroke_components(combined), detector_mode


def _prepare_stroke_crop(crop: np.ndarray) -> np.ndarray:
    if crop.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    if crop.ndim != 2:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if crop.dtype != np.uint8:
        crop = np.clip(crop, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(crop)


def _filter_stroke_components(mask: np.ndarray) -> np.ndarray:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros_like(mask)
    for label in range(1, num_labels):
        _x, _y, width, height, area = stats[label]
        if area < 6:
            continue
        longest = max(width, height)
        shortest = max(min(width, height), 1)
        elongated = longest / shortest >= 2.2
        dense_cluster = area >= 96 and longest >= 56 and shortest >= 24
        if area >= 18 or longest >= 14 or elongated or dense_cluster:
            filtered[labels == label] = 255
    return filtered


def _should_use_skeleton(mask: np.ndarray) -> bool:
    coords = np.column_stack(np.where(mask > 0))
    if len(coords) < 80:
        return False
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    width = int(x2 - x1 + 1)
    height = int(y2 - y1 + 1)
    if width < 60 or height < 40:
        return False
    fill_ratio = float(len(coords)) / max(float(width * height), 1.0)
    return fill_ratio >= 0.12


def _skeletonize_mask(mask: np.ndarray) -> np.ndarray:
    if hasattr(cv2, 'ximgproc') and hasattr(cv2.ximgproc, 'thinning'):
        return cv2.ximgproc.thinning(mask)

    skeleton = np.zeros_like(mask)
    working = mask.copy()
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while np.count_nonzero(working) > 0:
        eroded = cv2.erode(working, element)
        opened = cv2.dilate(eroded, element)
        residue = cv2.subtract(working, opened)
        skeleton = cv2.bitwise_or(skeleton, residue)
        working = eroded
    return skeleton


def _trace_mask_polyline(mask: np.ndarray, offset_x: float, offset_y: float) -> list[list[float]]:
    coords = np.column_stack(np.where(mask > 0))
    if len(coords) < 2:
        return _principal_polyline(coords, offset_x, offset_y)
    longest_path = _longest_skeleton_path(mask)
    if len(longest_path) < 2:
        return _principal_polyline(coords, offset_x, offset_y)
    sampled = _sample_path(longest_path)
    return _dedupe_points([
        [float(point[1] + offset_x), float(point[0] + offset_y)]
        for point in sampled
    ])


def _longest_skeleton_path(mask: np.ndarray) -> list[tuple[int, int]]:
    points = [tuple(point) for point in np.argwhere(mask > 0)]
    if len(points) < 2:
        return points
    point_set = set(points)
    endpoints = [point for point in points if len(_neighbors(point, point_set)) <= 1]
    start = endpoints[0] if endpoints else points[0]
    farthest, _ = _bfs_farthest(start, point_set)
    opposite, parents = _bfs_farthest(farthest, point_set)
    path: list[tuple[int, int]] = []
    current: tuple[int, int] | None = opposite
    while current is not None:
        path.append(current)
        current = parents.get(current)
    path.reverse()
    return path


def _bfs_farthest(
    start: tuple[int, int],
    point_set: set[tuple[int, int]],
) -> tuple[tuple[int, int], dict[tuple[int, int], tuple[int, int] | None]]:
    queue: deque[tuple[int, int]] = deque([start])
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    farthest = start
    while queue:
        point = queue.popleft()
        farthest = point
        for neighbor in _neighbors(point, point_set):
            if neighbor in parents:
                continue
            parents[neighbor] = point
            queue.append(neighbor)
    return farthest, parents


def _neighbors(point: tuple[int, int], point_set: set[tuple[int, int]]) -> list[tuple[int, int]]:
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


def _sample_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(path) <= 12:
        return path
    indices = np.linspace(0, len(path) - 1, num=12, dtype=np.int32)
    sampled = [path[int(index)] for index in indices]
    deduped: list[tuple[int, int]] = []
    for point in sampled:
        if deduped and deduped[-1] == point:
            continue
        deduped.append(point)
    return deduped


def _principal_polyline(coords: np.ndarray, offset_x: float, offset_y: float) -> list[list[float]]:
    points = coords[:, ::-1].astype(np.float32)
    center = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    axis = vt[0]
    proj = (points - center) @ axis

    bins = max(min(len(points) // 24, 8), 2)
    edges = np.linspace(float(proj.min()), float(proj.max()), num=bins + 1)
    sampled: list[list[float]] = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end == edges[-1]:
            chunk = points[(proj >= start) & (proj <= end)]
        else:
            chunk = points[(proj >= start) & (proj < end)]
        if len(chunk) == 0:
            continue
        avg = chunk.mean(axis=0)
        sampled.append([float(avg[0] + offset_x), float(avg[1] + offset_y)])

    if len(sampled) < 2:
        lo = points[int(np.argmin(proj))]
        hi = points[int(np.argmax(proj))]
        sampled = [
            [float(lo[0] + offset_x), float(lo[1] + offset_y)],
            [float(hi[0] + offset_x), float(hi[1] + offset_y)],
        ]
    return _dedupe_points(sampled)


def _estimate_width(mask: np.ndarray, points: list[list[float]]) -> float:
    foreground = float(np.count_nonzero(mask))
    path_len = 0.0
    for left, right in zip(points, points[1:]):
        dx = right[0] - left[0]
        dy = right[1] - left[1]
        path_len += (dx * dx + dy * dy) ** 0.5
    if path_len <= 1.0:
        return 1.0
    return max(foreground / path_len, 1.0)


def _absorb_endpoint_triangle(
    mask: np.ndarray,
    points: list[list[float]],
    bbox: list[int],
    width: float,
) -> tuple[dict[str, object] | None, int | None]:
    if len(points) < 2:
        return None, None
    best: tuple[float, dict[str, object], int] | None = None
    for endpoint_index, neighbor_index in ((0, 1), (-1, -2)):
        candidate = _detect_endpoint_triangle(mask, points, bbox, width, endpoint_index, neighbor_index)
        if candidate is None:
            continue
        score, arrow = candidate
        if best is None or score > best[0]:
            best = (score, arrow, endpoint_index)
    if best is None:
        return None, None
    return best[1], best[2]


def _detect_endpoint_triangle(
    mask: np.ndarray,
    points: list[list[float]],
    bbox: list[int],
    width: float,
    endpoint_index: int,
    neighbor_index: int,
) -> tuple[float, dict[str, object]] | None:
    x1, y1, _x2, _y2 = bbox
    local_tip = np.array([points[endpoint_index][0] - x1, points[endpoint_index][1] - y1], dtype=np.float32)
    local_prev = np.array([points[neighbor_index][0] - x1, points[neighbor_index][1] - y1], dtype=np.float32)
    direction = local_tip - local_prev
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-6:
        return None
    direction = direction / norm

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[float, dict[str, object]] | None = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < max(14.0, width * width * 1.5):
            continue
        perimeter = max(cv2.arcLength(contour, True), 1.0)
        approx = cv2.approxPolyDP(contour, max(2.0, perimeter * 0.05), True)
        if len(approx) != 3:
            continue
        vertices = approx.reshape(-1, 2).astype(np.float32)
        angles = [_triangle_vertex_angle(vertices, index) for index in range(3)]
        centroid = vertices.mean(axis=0)
        if np.linalg.norm(centroid - local_tip) > max(width * 10.0, 28.0):
            continue
        projections = vertices @ direction
        tip_idx = int(np.argmax(projections))
        acute_idx = int(np.argmin(angles))
        if tip_idx != acute_idx or angles[tip_idx] > 100.0:
            continue
        base = [vertices[index] for index in range(3) if index != tip_idx]
        tip = vertices[tip_idx]
        if np.linalg.norm(tip - local_tip) > max(width * 3.0, 12.0):
            continue
        tip_gain = float(projections[tip_idx] - np.mean([vertex @ direction for vertex in base]))
        if tip_gain < max(width * 1.2, 3.0):
            continue
        arrow = {
            'tip': [float(tip[0] + x1), float(tip[1] + y1)],
            'left': [float(base[0][0] + x1), float(base[0][1] + y1)],
            'right': [float(base[1][0] + x1), float(base[1][1] + y1)],
        }
        score = float(tip_gain - np.linalg.norm(centroid - local_tip) * 0.15)
        if best is None or score > best[0]:
            best = (score, arrow)
    return best


def _triangle_vertex_angle(vertices: np.ndarray, index: int) -> float:
    current = vertices[index]
    left = vertices[(index - 1) % 3] - current
    right = vertices[(index + 1) % 3] - current
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-6 or right_norm <= 1e-6:
        return 180.0
    cosine = float(np.dot(left, right) / (left_norm * right_norm))
    cosine = max(-1.0, min(1.0, cosine))
    return float(np.degrees(np.arccos(cosine)))


def _anchor_arrow_to_region(
    points: list[list[float]],
    width: float,
    region_nodes: list[SceneNode],
) -> tuple[dict[str, object] | None, int | None, str | None]:
    if len(points) < 2:
        return None, None, None
    best: tuple[float, dict[str, object], int, str] | None = None
    for endpoint_index, neighbor_index in ((0, 1), (-1, -2)):
        tip = np.array(points[endpoint_index], dtype=np.float32)
        neighbor = np.array(points[neighbor_index], dtype=np.float32)
        direction = tip - neighbor
        norm = float(np.linalg.norm(direction))
        if norm <= 1e-6:
            continue
        direction = direction / norm
        for region in region_nodes:
            gap = _point_bbox_gap(tip, region.bbox)
            if gap > max(width * 10.0, 16.0):
                continue
            center = np.array([
                (region.bbox[0] + region.bbox[2]) / 2.0,
                (region.bbox[1] + region.bbox[3]) / 2.0,
            ], dtype=np.float32)
            projection = float((center - neighbor) @ direction)
            if projection <= -max(width * 2.0, 6.0):
                continue
            arrow = _triangle_arrow_from_bbox(region.bbox, direction)
            score = projection - gap * 0.35
            if best is None or score > best[0]:
                best = (score, arrow, endpoint_index, region.id)
    if best is None:
        return None, None, None
    return best[1], best[2], best[3]


def _point_bbox_gap(point: np.ndarray, bbox: list[int]) -> float:
    x = float(point[0])
    y = float(point[1])
    dx = max(float(bbox[0]) - x, 0.0, x - float(bbox[2]))
    dy = max(float(bbox[1]) - y, 0.0, y - float(bbox[3]))
    return float((dx * dx + dy * dy) ** 0.5)


def _triangle_arrow_from_bbox(bbox: list[int], direction: np.ndarray) -> dict[str, object]:
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    if abs(float(direction[0])) >= abs(float(direction[1])):
        if float(direction[0]) >= 0.0:
            tip = [float(x2), float(cy)]
            left = [float(x1), float(y1)]
            right = [float(x1), float(y2)]
        else:
            tip = [float(x1), float(cy)]
            left = [float(x2), float(y1)]
            right = [float(x2), float(y2)]
    else:
        if float(direction[1]) >= 0.0:
            tip = [float(cx), float(y2)]
            left = [float(x1), float(y1)]
            right = [float(x2), float(y1)]
        else:
            tip = [float(cx), float(y1)]
            left = [float(x1), float(y2)]
            right = [float(x2), float(y2)]
    return {'tip': tip, 'left': left, 'right': right}


def _merge_debug_mask(debug_mask: np.ndarray, local_mask: np.ndarray, bbox: list[int]) -> None:
    if local_mask.size == 0:
        return
    x1, y1, x2, y2 = bbox
    target_width = max(x2 - x1, 1)
    target_height = max(y2 - y1, 1)
    if local_mask.shape[1] != target_width or local_mask.shape[0] != target_height:
        local_mask = cv2.resize(local_mask, (target_width, target_height), interpolation=cv2.INTER_NEAREST)
    region = debug_mask[y1:y2, x1:x2]
    np.maximum(region, local_mask, out=region)


def _constrain_arrow_head(
    arrow_head: dict[str, object] | None,
    width: float,
) -> dict[str, object] | None:
    if arrow_head is None:
        return None
    tip = np.array(arrow_head['tip'], dtype=np.float32)
    left = np.array(arrow_head['left'], dtype=np.float32)
    right = np.array(arrow_head['right'], dtype=np.float32)
    base_center = (left + right) / 2.0
    axis = base_center - tip
    axis_len = float(np.linalg.norm(axis))
    if axis_len <= 1e-6:
        return arrow_head

    axis_dir = axis / axis_len
    normal = np.array([-axis_dir[1], axis_dir[0]], dtype=np.float32)
    wing = max(float(np.linalg.norm(left - base_center)), float(np.linalg.norm(right - base_center)))
    max_length = max(width * 2.0, 10.0)
    max_wing = max(width * 1.0, 4.0)
    max_area = max(width * width * 1.8, 42.0)

    length = min(axis_len, max_length)
    wing = min(wing, max_wing)
    if length * wing > max_area:
        wing = min(wing, max_area / max(length, 1e-6))
    if length * wing > max_area:
        length = min(length, max_area / max(wing, 1e-6))

    new_base_center = tip + axis_dir * length
    left_pt = new_base_center + normal * wing
    right_pt = new_base_center - normal * wing
    return {
        'tip': [float(tip[0]), float(tip[1])],
        'left': [float(left_pt[0]), float(left_pt[1])],
        'right': [float(right_pt[0]), float(right_pt[1])],
    }


def _detect_arrow_head(
    coords: np.ndarray,
    points: list[list[float]],
    width: float,
) -> dict[str, object] | None:
    if len(points) < 2:
        return None

    xy = coords[:, ::-1].astype(np.float32)
    center = xy.mean(axis=0)
    _, _, vt = np.linalg.svd(xy - center, full_matrices=False)
    axis = vt[0]
    proj = (xy - center) @ axis
    hi = np.quantile(proj, 0.85)
    head = xy[proj >= hi]
    mid = xy[(proj > np.quantile(proj, 0.45)) & (proj < np.quantile(proj, 0.55))]
    if len(head) < 3 or len(mid) < 3:
        return None

    head_spread = float(np.std(head @ np.array([-axis[1], axis[0]], dtype=np.float32)))
    mid_spread = float(np.std(mid @ np.array([-axis[1], axis[0]], dtype=np.float32)))
    head_density = float(len(head))
    mid_density = float(len(mid))
    if head_spread < max(mid_spread * 1.1, width * 0.7) and head_density < mid_density * 1.15:
        return None

    tip = points[-1]
    prev = points[-2]
    dx = tip[0] - prev[0]
    dy = tip[1] - prev[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux
    base_x = tip[0] - ux * max(width * 2.4, 8.0)
    base_y = tip[1] - uy * max(width * 2.4, 8.0)
    wing = max(head_spread * 1.5, width * 1.2, 4.0)
    return {
        'tip': [tip[0], tip[1]],
        'left': [base_x + px * wing, base_y + py * wing],
        'right': [base_x - px * wing, base_y - py * wing],
    }


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for point in points:
        if deduped and abs(deduped[-1][0] - point[0]) < 0.5 and abs(deduped[-1][1] - point[1]) < 0.5:
            continue
        deduped.append(point)
    return deduped


def _load_gray_image(image_input: Path | np.ndarray) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return image_input
        return cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
    image = read_image(Path(image_input), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'Failed to read image: {image_input}')
    return image


def _extract_scaled_crop(image: np.ndarray, bbox: list[int], coordinate_scale: float) -> np.ndarray:
    x1, y1, x2, y2 = _scale_bbox(bbox, coordinate_scale, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0 or coordinate_scale == 1.0:
        return crop
    target_width = max(bbox[2] - bbox[0], 1)
    target_height = max(bbox[3] - bbox[1], 1)
    return cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_CUBIC)


def _scale_bbox(
    bbox: list[int],
    coordinate_scale: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    scaled = [int(round(coord * coordinate_scale)) for coord in bbox]
    x1, y1, x2, y2 = scaled
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2
