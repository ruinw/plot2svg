"""Stroke-based vectorization placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
from typing import Union

import numpy as np

from .image_io import read_image, write_image

from .scene_graph import SceneGraph, SceneNode
from .stroke_detector import detect_strokes


ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class StrokeVectorResult:
    """SVG fragment produced for a stroke component."""

    component_id: str
    svg_fragment: str
    curve_count: int


def vectorize_strokes(
    image_path: ImageInput,
    nodes: list[SceneNode],
    coordinate_scale: float = 1.0,
) -> list[StrokeVectorResult]:
    """Generate editable stroke polylines from stroke primitives."""

    if not nodes:
        return []
    width = max(node.bbox[2] for node in nodes)
    height = max(node.bbox[3] for node in nodes)
    graph = SceneGraph(width=width, height=height, nodes=nodes)
    primitives = detect_strokes(image_path, graph, coordinate_scale)
    results: list[StrokeVectorResult] = []
    emitted_node_ids: set[str] = set()
    for primitive in primitives:
        commands = [f"M {primitive.points[0][0]:.1f} {primitive.points[0][1]:.1f}"]
        for point in primitive.points[1:]:
            commands.append(f"L {point[0]:.1f} {point[1]:.1f}")
        results.append(
            StrokeVectorResult(
                component_id=primitive.node_id,
                svg_fragment=" ".join(commands),
                curve_count=max(len(primitive.points) - 1, 1),
            )
        )
        emitted_node_ids.add(primitive.node_id)

    if len(emitted_node_ids) == len([node for node in nodes if node.type == 'stroke']):
        return results

    gray_image = _load_gray_image(image_path)
    for node in nodes:
        if node.type != 'stroke' or node.id in emitted_node_ids:
            continue
        points = _fallback_stroke_points(gray_image, node.bbox, coordinate_scale)
        commands = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
        for point in points[1:]:
            commands.append(f"L {point[0]:.1f} {point[1]:.1f}")
        results.append(
            StrokeVectorResult(
                component_id=node.id,
                svg_fragment=" ".join(commands),
                curve_count=max(len(points) - 1, 1),
            )
        )
    return results



def _load_gray_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return image_input
        return cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
    image = read_image(Path(image_input), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image


def _fallback_stroke_points(image: np.ndarray, bbox: list[int], coordinate_scale: float) -> list[list[float]]:
    x1, y1, x2, y2 = _scale_bbox(bbox, coordinate_scale, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return [[float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]]
    _, mask = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(mask > 0))
    if len(coords) < 2:
        return [[float(bbox[0]), float(bbox[1])], [float(bbox[2]), float(bbox[3])]]
    return _principal_polyline(coords, float(bbox[0]), float(bbox[1]))


def _principal_polyline(coords: np.ndarray, offset_x: float, offset_y: float) -> list[list[float]]:
    points = coords[:, ::-1].astype(np.float32)
    center = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    axis = vt[0]
    projection = (points - center) @ axis
    bins = max(min(len(points) // 40, 8), 2)
    edges = np.linspace(float(projection.min()), float(projection.max()), num=bins + 1)
    sampled: list[list[float]] = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end == edges[-1]:
            chunk = points[(projection >= start) & (projection <= end)]
        else:
            chunk = points[(projection >= start) & (projection < end)]
        if len(chunk) == 0:
            continue
        avg = chunk.mean(axis=0)
        sampled.append([float(avg[0] + offset_x), float(avg[1] + offset_y)])
    if len(sampled) < 2:
        low = points[int(np.argmin(projection))]
        high = points[int(np.argmax(projection))]
        sampled = [
            [float(low[0] + offset_x), float(low[1] + offset_y)],
            [float(high[0] + offset_x), float(high[1] + offset_y)],
        ]
    return _dedupe_points(sampled)


def _dedupe_points(points: list[list[float]]) -> list[list[float]]:
    deduped: list[list[float]] = []
    for point in points:
        if deduped and abs(deduped[-1][0] - point[0]) < 0.5 and abs(deduped[-1][1] - point[1]) < 0.5:
            continue
        deduped.append(point)
    return deduped


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
