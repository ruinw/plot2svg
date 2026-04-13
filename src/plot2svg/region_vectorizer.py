"""Object-driven region vectorization with hole support."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .image_io import read_image, write_image

from .detect_shapes import SHAPE_CIRCLE, SHAPE_ELLIPSE, classify_contour
from .hierarchical_contours import collect_compound_subpaths, contour_path_commands, select_root_indices, subtree_indices
from .scene_graph import RegionObject, SceneGraph, SceneNode
from .svg_templates import extract_template_name


def vectorize_region_objects(
    image_input: Path | np.ndarray,
    scene_graph: SceneGraph,
    excluded_node_ids: set[str] | None = None,
    coordinate_scale: float = 1.0,
) -> list[RegionObject]:
    """Vectorize region nodes into mask-based region objects."""

    image = _load_color_image(image_input)
    excluded_node_ids = excluded_node_ids or set()
    objects: list[RegionObject] = []
    canvas_area = max(float(scene_graph.width * scene_graph.height), 1.0)
    for node in scene_graph.nodes:
        if node.type != 'region' or node.id == 'background-root' or node.id in excluded_node_ids:
            continue
        if node.shape_hint == 'svg_template':
            template_name = extract_template_name(node.component_role)
            if template_name is None:
                continue
            region_metadata = {
                'source': 'region_vectorizer',
                'entity_valid': True,
                'shape_type': 'svg_template',
                'template_name': template_name,
                'template_bbox': node.bbox[:],
            }
            objects.append(
                RegionObject(
                    id=f'region-object-{node.id}',
                    node_id=node.id,
                    outer_path=_rect_path(node.bbox),
                    holes=[],
                    fill=node.fill,
                    fill_opacity=node.fill_opacity,
                    stroke=node.stroke,
                    metadata=region_metadata,
                )
            )
            continue
        crop = _extract_scaled_crop(image, node.bbox, coordinate_scale)
        panel_rectangle = _detect_panel_rectangle(crop, node, node.bbox, canvas_area)
        if panel_rectangle is not None:
            outer_path, holes, metadata = panel_rectangle
        else:
            outer_path, holes, metadata = _trace_region(crop, node, node.bbox)
        region_metadata = {'source': 'region_vectorizer', 'entity_valid': True}
        region_metadata.update(metadata)
        objects.append(
            RegionObject(
                id=f'region-object-{node.id}',
                node_id=node.id,
                outer_path=outer_path,
                holes=holes,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                metadata=region_metadata,
            )
        )
    return objects


def _trace_region(
    crop: np.ndarray,
    node: SceneNode,
    bbox: list[int],
) -> tuple[str, list[str], dict[str, object]]:
    if crop.size == 0:
        return '', [], {'entity_valid': False, 'reject_reason': 'empty-crop'}

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = _filled_region_mask(crop, node)
    if mask is None:
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, raw_hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours or raw_hierarchy is None:
        return '', [], {'entity_valid': False, 'reject_reason': 'empty-mask'}

    hierarchy = raw_hierarchy[0]
    root_indices = select_root_indices(contours, hierarchy, mask.shape[:2], min_root_area=45.0)
    if not root_indices:
        return '', [], {'entity_valid': False, 'reject_reason': 'empty-mask'}

    primary_idx = root_indices[0]
    validity = _evaluate_region_entity(crop, contours[primary_idx], node)
    if not validity.get('entity_valid', True):
        return '', [], validity

    descendant_contours = _collect_descendant_contours(contours, hierarchy, primary_idx)
    use_compound_paths = _should_use_compound_region_paths(node, root_indices, descendant_contours)

    if use_compound_paths:
        outer_path = ''
        holes: list[str] = []
        compound_paths = collect_compound_subpaths(
            contours,
            hierarchy,
            root_indices,
            offset_x=bbox[0],
            offset_y=bbox[1],
            min_area=20.0,
            min_epsilon=1.5,
        )
        if not compound_paths:
            return '', [], {'entity_valid': False, 'reject_reason': 'empty-compound-path'}
        outer_path = compound_paths[0]
        holes = compound_paths[1:]
    else:
        outer_path = _simple_contour_path(contours[primary_idx], bbox[0], bbox[1])
        holes = [_simple_contour_path(contour, bbox[0], bbox[1]) for contour in descendant_contours]

    ellipse_meta = None
    if len(root_indices) == 1:
        ellipse_meta = _fit_region_ellipse(mask, contours[primary_idx], descendant_contours, bbox)
    if ellipse_meta is not None:
        shape_type = 'circle' if ellipse_meta.get('is_circle') else 'ellipse'
        return outer_path, holes, {
            'entity_valid': True,
            'shape_type': shape_type,
            'circle': ellipse_meta.get('circle'),
            'ellipse': ellipse_meta,
            'fit_error': ellipse_meta['fit_error'],
            'contrast_to_surround': validity['contrast_to_surround'],
            'contrast_to_white': validity['contrast_to_white'],
            'root_count': len(root_indices),
            'compound_path_count': 1 + len(holes),
        }

    validity = dict(validity)
    validity['root_count'] = len(root_indices)
    validity['compound_path_count'] = 1 + len(holes)
    return outer_path, holes, validity


def _evaluate_region_entity(
    crop: np.ndarray,
    contour: np.ndarray,
    node: SceneNode,
) -> dict[str, object]:
    solid_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.drawContours(solid_mask, [contour], -1, 255, -1)
    region_pixels = crop[solid_mask > 0]
    if region_pixels.size == 0:
        return {'entity_valid': False, 'reject_reason': 'empty-region'}

    ring_mask = cv2.dilate(solid_mask, np.ones((5, 5), dtype=np.uint8), iterations=1)
    ring_mask = cv2.subtract(ring_mask, solid_mask)
    ring_pixels = crop[ring_mask > 0]

    region_mean = region_pixels.mean(axis=0)
    surround_mean = ring_pixels.mean(axis=0) if ring_pixels.size else np.full(3, 255.0, dtype=np.float32)
    surround_gap = float(np.linalg.norm(region_mean - surround_mean))
    white_gap = float(np.linalg.norm(region_mean - 255.0))
    black_gap = float(np.linalg.norm(region_mean - 0.0))
    brightness = float(np.mean(region_mean))

    area = float(cv2.contourArea(contour))
    _x, _y, width, height = cv2.boundingRect(contour)
    fill_ratio = area / max(float(width * height), 1.0)
    aspect_ratio = max(width, 1) / max(height, 1)
    aspect_ratio = max(aspect_ratio, 1.0 / max(aspect_ratio, 1e-6))
    extreme_shape = fill_ratio < 0.35 or aspect_ratio >= 6.0
    tiny_fragment = area < 400.0

    near_white = brightness >= 246.0 and white_gap <= 18.0 and surround_gap <= 18.0
    near_black = brightness <= 12.0 and black_gap <= 24.0 and surround_gap <= 28.0

    if (near_white or near_black) and extreme_shape and tiny_fragment:
        return {
            'entity_valid': False,
            'reject_reason': 'extreme-monochrome-fragment',
            'contrast_to_surround': round(surround_gap, 3),
            'contrast_to_white': round(white_gap, 3),
        }

    return {
        'entity_valid': True,
        'contrast_to_surround': round(surround_gap, 3),
        'contrast_to_white': round(white_gap, 3),
    }


def _collect_descendant_contours(
    contours: list[np.ndarray],
    hierarchy: np.ndarray,
    root_idx: int,
) -> list[np.ndarray]:
    descendants: list[np.ndarray] = []
    for index in subtree_indices(root_idx, hierarchy):
        if index == root_idx:
            continue
        if cv2.contourArea(contours[index]) >= 20:
            descendants.append(contours[index])
    return descendants


def _fill_brightness(fill: str) -> float:
    red = int(fill[1:3], 16)
    green = int(fill[3:5], 16)
    blue = int(fill[5:7], 16)
    return (red + green + blue) / 3.0


def _should_use_compound_region_paths(
    node: SceneNode,
    root_indices: list[int],
    descendant_contours: list[np.ndarray],
) -> bool:
    fill = (node.fill or '').lower()
    if fill in {'', 'none'}:
        return True
    brightness = _fill_brightness(fill)
    if brightness <= 96.0:
        return True
    if len(root_indices) > 1 and brightness <= 160.0:
        return True
    if len(descendant_contours) > 4:
        return True
    return False


def _fit_region_ellipse(
    mask: np.ndarray,
    contour: np.ndarray,
    hole_contours: list[np.ndarray],
    bbox: list[int],
) -> dict[str, float] | None:
    area = float(cv2.contourArea(contour))
    if area < 1800 or len(contour) < 5:
        return None

    hole_area = sum(float(cv2.contourArea(hole)) for hole in hole_contours)
    largest_hole_area = max((float(cv2.contourArea(hole)) for hole in hole_contours), default=0.0)
    hole_ratio = hole_area / max(area, 1.0)
    largest_hole_ratio = largest_hole_area / max(area, 1.0)
    simple_hole_count = sum(
        1
        for hole in hole_contours
        if classify_contour(hole) in {SHAPE_CIRCLE, SHAPE_ELLIPSE, 'rectangle', 'polygon'}
    )

    if (
        hole_contours
        and len(hole_contours) <= 4
        and simple_hole_count == len(hole_contours)
        and (
            hole_ratio >= 0.22
            or largest_hole_ratio >= 0.12
            or (len(hole_contours) >= 2 and hole_ratio >= 0.10)
        )
    ):
        return None

    solid_mask = np.zeros_like(mask)
    cv2.drawContours(solid_mask, [contour], -1, 255, -1)
    solid_contours, _ = cv2.findContours(solid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not solid_contours:
        return None
    solid_contour = max(solid_contours, key=cv2.contourArea)
    if len(solid_contour) < 5:
        return None

    solid_area = float(cv2.contourArea(solid_contour))
    shape_type = classify_contour(solid_contour)

    try:
        (cx, cy), (axis_a, axis_b), angle = cv2.fitEllipse(solid_contour)
    except cv2.error:
        return None
    rx = float(axis_a / 2.0)
    ry = float(axis_b / 2.0)
    if rx < ry:
        rx, ry = ry, rx
        angle += 90.0
    angle = ((float(angle) + 90.0) % 180.0) - 90.0
    if min(rx, ry) < 18.0:
        return None

    ellipse_mask = np.zeros_like(mask)
    cv2.ellipse(
        ellipse_mask,
        (int(round(cx)), int(round(cy))),
        (max(int(round(rx)), 1), max(int(round(ry)), 1)),
        float(angle),
        0,
        360,
        255,
        -1,
    )
    ellipse_binary = ellipse_mask > 0
    mask_binary = solid_mask > 0
    union = float(np.count_nonzero(mask_binary | ellipse_binary))
    if union <= 0.0:
        return None
    intersection = float(np.count_nonzero(mask_binary & ellipse_binary))
    iou = intersection / union
    ellipse_area = math.pi * rx * ry
    area_ratio = solid_area / max(ellipse_area, 1.0)
    fit_error = 1.0 - iou

    fit_is_elliptic = iou >= 0.72 and 0.62 <= area_ratio <= 1.18
    if shape_type not in {SHAPE_CIRCLE, SHAPE_ELLIPSE} and not fit_is_elliptic:
        return None
    if iou < 0.72 or not 0.62 <= area_ratio <= 1.2:
        return None

    circle_like = abs(rx - ry) / max(rx, ry, 1.0) <= 0.08
    circle_radius = (rx + ry) / 2.0

    return {
        'cx': round(float(cx + bbox[0]), 3),
        'cy': round(float(cy + bbox[1]), 3),
        'rx': round(rx, 3),
        'ry': round(ry, 3),
        'rotation': round(float(angle), 3),
        'fit_error': round(fit_error, 4),
        'is_circle': circle_like,
        'circle': {
            'cx': round(float(cx + bbox[0]), 3),
            'cy': round(float(cy + bbox[1]), 3),
            'r': round(circle_radius, 3),
        } if circle_like else None,
    }



def _detect_panel_rectangle(
    crop: np.ndarray,
    node: SceneNode,
    bbox: list[int],
    canvas_area: float,
) -> tuple[str, list[str], dict[str, object]] | None:
    if crop.size == 0:
        return None

    x1, y1, x2, y2 = bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    bbox_area = float(width * height)
    if bbox_area < canvas_area * 0.05:
        return None

    if node.shape_hint == 'panel':
        return (
            _rect_path(bbox),
            [],
            {
                'entity_valid': True,
                'shape_type': 'rectangle',
                'rectangle': {
                    'x': float(x1),
                    'y': float(y1),
                    'width': float(width),
                    'height': float(height),
                },
                'panel_detected': True,
                'panel_fill_ratio': 1.0,
            },
        )

    fill_mask = _panel_fill_mask(crop, node)
    if fill_mask is None:
        return None

    contours, _ = cv2.findContours(fill_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    fill_ratio = float(cv2.contourArea(largest)) / max(bbox_area, 1.0)
    if fill_ratio <= 0.9:
        return None

    return (
        _rect_path(bbox),
        [],
        {
            'entity_valid': True,
            'shape_type': 'rectangle',
            'rectangle': {
                'x': float(x1),
                'y': float(y1),
                'width': float(width),
                'height': float(height),
            },
            'panel_detected': True,
            'panel_fill_ratio': round(fill_ratio, 4),
        },
    )


def _panel_fill_mask(crop: np.ndarray, node: SceneNode) -> np.ndarray | None:
    fill_mask = _filled_region_mask(crop, node)
    if fill_mask is None:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        non_white = ((gray < 245) | (hsv[:, :, 1] > 14)).astype(np.uint8) * 255
        fill_mask = non_white
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    fill_mask = cv2.morphologyEx(fill_mask, cv2.MORPH_CLOSE, kernel)
    fill_mask = cv2.morphologyEx(fill_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    if np.count_nonzero(fill_mask) == 0:
        return None
    return fill_mask

def _filled_region_mask(crop: np.ndarray, node: SceneNode) -> np.ndarray | None:
    fill = (node.fill or '').lower()
    if fill in {'', 'none', '#ffffff'}:
        return None

    fill_bgr = np.array(
        [int(fill[5:7], 16), int(fill[3:5], 16), int(fill[1:3], 16)],
        dtype=np.float32,
    )
    diff = np.linalg.norm(crop.astype(np.float32) - fill_bgr, axis=2)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    non_white = gray < 242
    mask = ((diff <= 58.0) & non_white).astype(np.uint8) * 255
    if float(np.mean(mask > 0)) < 0.04:
        return None
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def _simple_contour_path(contour: np.ndarray, offset_x: int, offset_y: int) -> str:
    epsilon = max(1.5, 0.01 * cv2.arcLength(contour, True))
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        approx = contour
    points = approx[:, 0, :]
    commands = [f'M {int(points[0][0] + offset_x)} {int(points[0][1] + offset_y)}']
    for pt in points[1:]:
        commands.append(f'L {int(pt[0] + offset_x)} {int(pt[1] + offset_y)}')
    commands.append('Z')
    return ' '.join(commands)


def _rect_path(bbox: list[int]) -> str:
    x1, y1, x2, y2 = bbox
    return f'M {x1} {y1} L {x2} {y1} L {x2} {y2} L {x1} {y2} Z'


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
