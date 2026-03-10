"""Stroke-based vectorization placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from .gpu import gaussian_blur, threshold
from .scene_graph import SceneNode


ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class StrokeVectorResult:
    """SVG fragment produced for a stroke component."""

    component_id: str
    svg_fragment: str
    curve_count: int


def vectorize_strokes(image_path: ImageInput, nodes: list[SceneNode]) -> list[StrokeVectorResult]:
    """Generate stroke SVG fragments from real image regions."""

    image = _load_gray_image(image_path)
    results: list[StrokeVectorResult] = []
    for node in nodes:
        if node.type != "stroke":
            continue
        x1, y1, x2, y2 = _clamp_bbox(node.bbox, image.shape[1], image.shape[0])
        crop = image[y1:y2, x1:x2]
        fragment, curve_count = _trace_stroke_crop(crop, x1, y1)
        results.append(
            StrokeVectorResult(
                component_id=node.id,
                svg_fragment=fragment,
                curve_count=curve_count,
            )
        )
    return results


def _trace_stroke_crop(crop: np.ndarray, offset_x: int, offset_y: int) -> tuple[str, int]:
    if crop.size == 0:
        return f"M {offset_x} {offset_y} L {offset_x + 1} {offset_y + 1}", 1

    blurred = gaussian_blur(crop, (3, 3), 0)
    _, binary = threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    refined = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(refined, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    path_parts: list[str] = []
    kept = 0
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < 4:
            continue
        approx = cv2.approxPolyDP(contour, epsilon=1.5, closed=False)
        if len(approx) < 2:
            continue
        points = approx[:, 0, :]
        commands = [f"M {int(points[0][0] + offset_x)} {int(points[0][1] + offset_y)}"]
        for point in points[1:]:
            commands.append(f"L {int(point[0] + offset_x)} {int(point[1] + offset_y)}")
        path_parts.append(" ".join(commands))
        kept += 1
        if kept >= 32:
            break

    if not path_parts:
        height, width = crop.shape[:2]
        return f"M {offset_x} {offset_y} L {offset_x + max(width - 1, 1)} {offset_y + max(height - 1, 1)}", 1

    return " ".join(path_parts), kept


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _load_gray_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return image_input
        return cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
    image = cv2.imread(str(Path(image_input)), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image
