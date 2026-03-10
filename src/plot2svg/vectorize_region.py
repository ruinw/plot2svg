"""Region-based vectorization placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from .gpu import canny, gaussian_blur, threshold
from .scene_graph import SceneNode


ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class RegionVectorResult:
    """SVG fragment produced for a region component."""

    component_id: str
    svg_fragment: str
    path_count: int
    simplified: bool


def vectorize_regions(image_path: ImageInput, nodes: list[SceneNode]) -> list[RegionVectorResult]:
    """Generate region SVG fragments from real image regions."""

    image = _load_color_image(image_path)
    results: list[RegionVectorResult] = []
    for node in nodes:
        if node.type != "region":
            continue
        x1, y1, x2, y2 = _clamp_bbox(node.bbox, image.shape[1], image.shape[0])
        crop = image[y1:y2, x1:x2]
        fragment, path_count = _trace_region_crop(crop, x1, y1, node)
        results.append(
            RegionVectorResult(
                component_id=node.id,
                svg_fragment=fragment,
                path_count=path_count,
                simplified=True,
            )
        )
    return results


def _trace_region_crop(crop: np.ndarray, offset_x: int, offset_y: int, node: SceneNode) -> tuple[str, int]:
    if crop.size == 0:
        return _fallback_region_path(node, offset_x, offset_y, 1, 1), 1

    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = gaussian_blur(gray, (5, 5), 0)
        edges = canny(blurred, 80, 160)
        _, thresh = threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        combined = cv2.bitwise_or(edges, cv2.bitwise_not(thresh))
        kernel = np.ones((3, 3), np.uint8)
        refined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(refined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except cv2.error:
        height, width = crop.shape[:2]
        return _fallback_region_path(node, offset_x, offset_y, width, height), 1

    fragments: list[str] = []
    kept = 0
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < 24:
            continue
        epsilon = max(1.5, 0.01 * cv2.arcLength(contour, True))
        approx = cv2.approxPolyDP(contour, epsilon=epsilon, closed=True)
        if len(approx) < 3:
            continue
        points = approx[:, 0, :]
        commands = [f"M {int(points[0][0] + offset_x)} {int(points[0][1] + offset_y)}"]
        for point in points[1:]:
            commands.append(f"L {int(point[0] + offset_x)} {int(point[1] + offset_y)}")
        commands.append("Z")
        path_data = " ".join(commands)
        fragments.append(
            f"<path id='{node.id}-{kept}' d='{path_data}' fill='{node.fill or 'none'}' stroke='{node.stroke or '#000000'}' />"
        )
        kept += 1
        if kept >= 24:
            break

    if not fragments:
        height, width = crop.shape[:2]
        return _fallback_region_path(node, offset_x, offset_y, width, height), 1

    return " ".join(fragments), kept


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _fallback_region_path(node: SceneNode, offset_x: int, offset_y: int, width: int, height: int) -> str:
    return (
        f"<path id='{node.id}-fallback' d='M {offset_x} {offset_y} "
        f"L {offset_x + max(width - 1, 1)} {offset_y} "
        f"L {offset_x + max(width - 1, 1)} {offset_y + max(height - 1, 1)} "
        f"L {offset_x} {offset_y + max(height - 1, 1)} Z' "
        f"fill='{node.fill or 'none'}' stroke='{node.stroke or '#000000'}' />"
    )


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = cv2.imread(str(Path(image_input)), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image
