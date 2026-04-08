"""Object-driven node detection."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .image_io import read_image, write_image

from .detect_shapes import SHAPE_CIRCLE, SHAPE_TRIANGLE, classify_contour
from .scene_graph import NodeObject, SceneGraph

_POLYGON_SHAPES = {'triangle', 'pentagon'}


def detect_nodes(
    image_input: Path | np.ndarray,
    scene_graph: SceneGraph,
    coordinate_scale: float = 1.0,
) -> list[NodeObject]:
    """Promote geometric regions into explicit node objects."""

    image = _load_color_image(image_input)
    detected: list[NodeObject] = []
    for node in scene_graph.nodes:
        if node.type != 'region' or node.id == 'background-root':
            continue
        crop = _extract_scaled_crop(image, node.bbox, coordinate_scale)
        if crop.size == 0:
            continue
        result = _detect_single_node(crop, node.bbox, hinted=node.shape_hint)
        if result is None:
            continue
        fill = node.fill or _sample_fill(crop)
        metadata = {
            'source': 'node_detector',
            'shape_hint': node.shape_hint or result['shape_type'],
            'shape_type': result['shape_type'],
            'vertex_count': result.get('vertex_count'),
            'size': result['size'],
            'orientation': result.get('orientation'),
        }
        detected.append(
            NodeObject(
                id=f'node-{node.id}',
                node_id=node.id,
                center=result['center'],
                radius=result['radius'],
                fill=fill,
                metadata=metadata,
            )
        )
    return _suppress_near_duplicates(detected)


def _detect_single_node(
    crop: np.ndarray,
    bbox: list[int],
    hinted: str | None,
) -> dict[str, object] | None:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if hinted in {None, SHAPE_CIRCLE}:
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(min(crop.shape[:2]) // 4, 8),
            param1=90,
            param2=14,
            minRadius=max(min(crop.shape[:2]) // 8, 4),
            maxRadius=max(min(crop.shape[:2]) // 2, 6),
        )
        if circles is not None and len(circles[0]) > 0:
            cx, cy, radius = circles[0][0]
            return {
                'center': [bbox[0] + float(cx), bbox[1] + float(cy)],
                'radius': float(radius),
                'shape_type': SHAPE_CIRCLE,
                'vertex_count': None,
                'size': {'width': float(radius * 2.0), 'height': float(radius * 2.0)},
                'orientation': None,
            }

    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    polygon = _detect_polygon_node(contour, bbox, hinted)
    if polygon is not None:
        return polygon

    area = cv2.contourArea(contour)
    perimeter = max(cv2.arcLength(contour, True), 1.0)
    circularity = 4.0 * np.pi * area / (perimeter * perimeter)
    if hinted not in {None, SHAPE_CIRCLE} and hinted not in _POLYGON_SHAPES:
        return None
    if hinted != SHAPE_CIRCLE and circularity < 0.7:
        return None

    (cx, cy), radius = cv2.minEnclosingCircle(contour)
    if radius < 4:
        return None
    x, y, w, h = cv2.boundingRect(contour)
    return {
        'center': [bbox[0] + float(cx), bbox[1] + float(cy)],
        'radius': float(radius),
        'shape_type': SHAPE_CIRCLE,
        'vertex_count': None,
        'size': {'width': float(w), 'height': float(h)},
        'orientation': None,
    }


def _detect_polygon_node(
    contour: np.ndarray,
    bbox: list[int],
    hinted: str | None,
) -> dict[str, object] | None:
    area = cv2.contourArea(contour)
    if area < 24:
        return None
    perimeter = max(cv2.arcLength(contour, True), 1.0)
    epsilon = max(2.0, perimeter * 0.03)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    vertex_count = len(approx)
    if not cv2.isContourConvex(approx):
        return None

    shape_type: str | None = None
    if vertex_count == 3:
        shape_type = SHAPE_TRIANGLE
    elif vertex_count == 5:
        shape_type = 'pentagon'
    elif hinted in _POLYGON_SHAPES:
        shape_type = hinted
    else:
        classified = classify_contour(contour)
        if classified == SHAPE_TRIANGLE:
            shape_type = SHAPE_TRIANGLE

    if shape_type not in _POLYGON_SHAPES:
        return None

    moments = cv2.moments(contour)
    if abs(moments['m00']) > 1e-6:
        cx = moments['m10'] / moments['m00']
        cy = moments['m01'] / moments['m00']
    else:
        x, y, w, h = cv2.boundingRect(contour)
        cx = x + (w / 2.0)
        cy = y + (h / 2.0)
    x, y, w, h = cv2.boundingRect(contour)
    orientation = _infer_polygon_orientation(approx, shape_type, (cx, cy))
    return {
        'center': [bbox[0] + float(cx), bbox[1] + float(cy)],
        'radius': float(max(w, h) / 2.0),
        'shape_type': shape_type,
        'vertex_count': 3 if shape_type == SHAPE_TRIANGLE else 5,
        'size': {'width': float(w), 'height': float(h)},
        'orientation': orientation,
    }


def _infer_polygon_orientation(
    approx: np.ndarray,
    shape_type: str,
    centroid: tuple[float, float],
) -> dict[str, object] | None:
    if shape_type != SHAPE_TRIANGLE or len(approx) < 3:
        return None
    points = approx.reshape(-1, 2).astype(np.float32)
    centroid_vec = np.array(centroid, dtype=np.float32)
    distances = np.linalg.norm(points - centroid_vec, axis=1)
    apex = points[int(np.argmax(distances))]
    vector = apex - centroid_vec
    angle = math.degrees(math.atan2(float(vector[1]), float(vector[0])))
    return {
        'direction': _angle_to_direction(angle),
        'angle_degrees': round(angle, 3),
        'vector': [round(float(vector[0]), 3), round(float(vector[1]), 3)],
        'apex': [round(float(apex[0]), 3), round(float(apex[1]), 3)],
    }


def _angle_to_direction(angle: float) -> str:
    if -135.0 <= angle < -45.0:
        return 'up'
    if -45.0 <= angle < 45.0:
        return 'right'
    if 45.0 <= angle < 135.0:
        return 'down'
    return 'left'


def _suppress_near_duplicates(nodes: list[NodeObject]) -> list[NodeObject]:
    ordered = sorted(nodes, key=_node_priority, reverse=True)
    kept: list[NodeObject] = []
    for node in ordered:
        duplicate_of = next((existing for existing in kept if _should_suppress(existing, node)), None)
        if duplicate_of is None:
            kept.append(node)
            continue
        suppressed = list(duplicate_of.metadata.get('suppressed_source_ids', []))
        suppressed.append(node.node_id)
        duplicate_of.metadata['suppressed_source_ids'] = suppressed
    return sorted(kept, key=lambda item: (item.center[1], item.center[0], item.node_id))


def _should_suppress(existing: NodeObject, candidate: NodeObject) -> bool:
    if _is_duplicate_node(existing, candidate):
        return True
    return _is_nested_hough_noise(existing, candidate)


def _node_priority(node: NodeObject) -> tuple[float, float, float]:
    width, height = _node_size(node)
    area = width * height
    source_bonus = 1.0 if not node.node_id.startswith('region-hough-') else 0.0
    shape_bonus = 0.25 if node.metadata.get('shape_type') in _POLYGON_SHAPES else 0.0
    return (source_bonus + shape_bonus, area, node.radius)


def _is_duplicate_node(left: NodeObject, right: NodeObject) -> bool:
    if left.metadata.get('shape_type') != right.metadata.get('shape_type'):
        return False
    left_bbox = _node_bbox(left)
    right_bbox = _node_bbox(right)
    overlap = _bbox_overlap_ratio(left_bbox, right_bbox)
    center_distance = math.hypot(left.center[0] - right.center[0], left.center[1] - right.center[1])
    left_width, left_height = _node_size(left)
    right_width, right_height = _node_size(right)
    size_ratio = min(left_width * left_height, right_width * right_height) / max(left_width * left_height, right_width * right_height, 1.0)
    if overlap >= 0.78 and size_ratio >= 0.6:
        return True
    near_limit = min(max(left.radius, 6.0), max(right.radius, 6.0)) * 0.7
    if center_distance <= near_limit and size_ratio >= 0.85:
        return True
    return False


def _is_nested_hough_noise(existing: NodeObject, candidate: NodeObject) -> bool:
    if not candidate.node_id.startswith('region-hough-'):
        return False
    if existing.node_id.startswith('region-hough-'):
        return False
    if existing.metadata.get('shape_type') != SHAPE_CIRCLE or candidate.metadata.get('shape_type') != SHAPE_CIRCLE:
        return False
    if candidate.radius > existing.radius * 0.4:
        return False
    center_distance = math.hypot(existing.center[0] - candidate.center[0], existing.center[1] - candidate.center[1])
    return center_distance + candidate.radius <= existing.radius * 0.95


def _node_bbox(node: NodeObject) -> tuple[float, float, float, float]:
    width, height = _node_size(node)
    half_width = width / 2.0
    half_height = height / 2.0
    return (
        node.center[0] - half_width,
        node.center[1] - half_height,
        node.center[0] + half_width,
        node.center[1] + half_height,
    )


def _node_size(node: NodeObject) -> tuple[float, float]:
    size = node.metadata.get('size') or {}
    width = float(size.get('width', node.radius * 2.0))
    height = float(size.get('height', node.radius * 2.0))
    return max(width, 1.0), max(height, 1.0)


def _bbox_overlap_ratio(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1.0)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1.0)
    return intersection / min(left_area, right_area)


def _sample_fill(crop: np.ndarray) -> str | None:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = gray < 242
    if not np.any(mask):
        return None
    pixels = crop[mask].reshape(-1, 3).astype(np.int32)
    mean = np.clip(np.mean(pixels, axis=0), 0, 255).astype(np.uint8)
    b, g, r = [int(channel) for channel in mean]
    return f'#{r:02x}{g:02x}{b:02x}'


def _load_color_image(image_input: Path | np.ndarray) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
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
