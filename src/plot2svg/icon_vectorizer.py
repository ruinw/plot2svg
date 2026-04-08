"""Compound-path icon vectorization helpers."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

VECTOR_BLUR = 1
VECTOR_CLOSE_KERNEL = 0
VECTOR_EPSILON_RATIO = 0.005
MIN_VECTOR_AREA = 20.0
MIN_INNER_VECTOR_AREA = 5.0
MAX_VECTOR_OBJECTS = 12
MAX_INNER_OBJECTS = 64
INNER_VECTOR_EPSILON_RATIO = 0.005


@dataclass(frozen=True, slots=True)
class IconVectorization:
    compound_path: str
    contour_paths: list[str]
    outer_count: int
    inner_count: int


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def approximate_contour(contour: np.ndarray, epsilon_ratio: float = VECTOR_EPSILON_RATIO) -> np.ndarray:
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(1.0, perimeter * epsilon_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = approx.reshape(-1, 2) if len(approx) >= 3 else contour.reshape(-1, 2)
    return points


def points_to_path(points: np.ndarray) -> str:
    coords = [f'{int(x)},{int(y)}' for x, y in points]
    if not coords:
        return ''
    return 'M ' + ' L '.join(coords) + ' Z'


def contour_depth(index: int, hierarchy: np.ndarray) -> int:
    depth = 0
    parent = hierarchy[index][3]
    while parent != -1:
        depth += 1
        parent = hierarchy[parent][3]
    return depth


def bbox_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int], margin: int = 2) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ox - margin <= ix and oy - margin <= iy and ox + ow + margin >= ix + iw and oy + oh + margin >= iy + ih


def vectorize_clean_image(image: np.ndarray) -> IconVectorization | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_size = max(1, ensure_odd(VECTOR_BLUR))
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0) if blur_size > 1 else gray.copy()
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if VECTOR_CLOSE_KERNEL > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (ensure_odd(VECTOR_CLOSE_KERNEL), ensure_odd(VECTOR_CLOSE_KERNEL)),
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, raw_hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if raw_hierarchy is None or not contours:
        return None
    hierarchy = raw_hierarchy[0]

    outer_indices = [idx for idx, h in enumerate(hierarchy) if h[3] == -1 and cv2.contourArea(contours[idx]) >= MIN_VECTOR_AREA]
    outer_indices.sort(key=lambda idx: cv2.contourArea(contours[idx]), reverse=True)
    outer_indices = outer_indices[:MAX_VECTOR_OBJECTS]
    if not outer_indices:
        return None

    outer_paths: list[str] = []
    outer_bboxes: list[tuple[int, int, int, int]] = []
    for idx in outer_indices:
        path = points_to_path(approximate_contour(contours[idx], VECTOR_EPSILON_RATIO))
        if path:
            outer_paths.append(path)
            outer_bboxes.append(tuple(int(v) for v in cv2.boundingRect(contours[idx])))

    inner_candidates: list[tuple[float, str]] = []
    for idx, contour in enumerate(contours):
        if idx in outer_indices:
            continue
        area = cv2.contourArea(contour)
        if area < MIN_INNER_VECTOR_AREA:
            continue
        bbox = tuple(int(v) for v in cv2.boundingRect(contour))
        if not any(bbox_contains(outer_bbox, bbox) for outer_bbox in outer_bboxes):
            continue
        if contour_depth(idx, hierarchy) <= 0:
            continue
        path = points_to_path(approximate_contour(contour, INNER_VECTOR_EPSILON_RATIO))
        if path:
            inner_candidates.append((area, path))

    inner_candidates.sort(key=lambda item: item[0], reverse=True)
    inner_paths = [path for _area, path in inner_candidates[:MAX_INNER_OBJECTS]]
    contour_paths = [*outer_paths, *inner_paths]
    compound_path = ' '.join(path for path in contour_paths if path)
    if not compound_path:
        return None
    return IconVectorization(
        compound_path=compound_path,
        contour_paths=contour_paths,
        outer_count=len(outer_paths),
        inner_count=len(inner_paths),
    )
