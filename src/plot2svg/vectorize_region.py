"""Region-based vectorization placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from .image_io import read_image, write_image

from .detect_shapes import contour_to_svg_element
from .hierarchical_contours import collect_compound_subpaths, contour_path_commands, select_root_indices
from .gpu import canny, gaussian_blur, threshold
from .region_vectorizer import vectorize_region_objects
from .scene_graph import SceneGraph, SceneNode


ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class RegionVectorResult:
    """SVG fragment produced for a region component."""

    component_id: str
    svg_fragment: str
    path_count: int
    simplified: bool


@dataclass(slots=True)
class _ContourExtractionResult:
    """Contours extracted from a region crop."""

    contours: list[np.ndarray]
    hierarchy: np.ndarray | None = None
    force_complex_path: bool = False


def vectorize_regions(
    image_path: ImageInput,
    nodes: list[SceneNode],
    coordinate_scale: float = 1.0,
) -> list[RegionVectorResult]:
    """Generate region SVG fragments while delegating core tracing to object vectorization."""

    if not nodes:
        return []
    image = _load_color_image(image_path)
    width = max(node.bbox[2] for node in nodes)
    height = max(node.bbox[3] for node in nodes)
    graph = SceneGraph(width=width, height=height, nodes=nodes)
    region_objects = vectorize_region_objects(image, graph, coordinate_scale=coordinate_scale)
    object_map = {obj.node_id: obj for obj in region_objects}

    results: list[RegionVectorResult] = []
    for node in nodes:
        if node.type != "region":
            continue
        if node.shape_hint == "circle":
            cx = (node.bbox[0] + node.bbox[2]) / 2.0
            cy = (node.bbox[1] + node.bbox[3]) / 2.0
            radius = max(min(node.bbox[2] - node.bbox[0], node.bbox[3] - node.bbox[1]) / 2.0, 1.0)
            fill_attr = (
                f" fill-opacity='{node.fill_opacity:.3f}'"
                if node.fill_opacity is not None and node.fill_opacity < 0.999
                else ""
            )
            fragment = (
                f"<circle id='{node.id}-0' cx='{cx:.1f}' cy='{cy:.1f}' r='{radius:.1f}' "
                f"fill='{node.fill or 'none'}' stroke='{node.stroke or '#000000'}'{fill_attr} />"
            )
            results.append(
                RegionVectorResult(
                    component_id=node.id,
                    svg_fragment=fragment,
                    path_count=1,
                    simplified=False,
                )
            )
            continue

        region_obj = object_map.get(node.id)
        if region_obj is not None:
            geometry_fragment = _render_region_geometry_fragment(node.id, region_obj)
            if geometry_fragment is not None:
                results.append(
                    RegionVectorResult(
                        component_id=node.id,
                        svg_fragment=geometry_fragment,
                        path_count=1,
                        simplified=False,
                    )
                )
                continue
        if region_obj is not None and region_obj.outer_path:
            commands = [region_obj.outer_path, *region_obj.holes]
            fill_attr = (
                f" fill-opacity='{region_obj.fill_opacity:.3f}'"
                if region_obj.fill_opacity is not None and region_obj.fill_opacity < 0.999
                else ""
            )
            fill_rule = " fill-rule='evenodd'" if region_obj.holes else ""
            fragment = (
                f"<path id='{node.id}-0' d='{' '.join(commands)}' fill='{region_obj.fill or 'none'}' "
                f"stroke='{region_obj.stroke or '#000000'}'{fill_attr}{fill_rule} />"
            )
            results.append(
                RegionVectorResult(
                    component_id=node.id,
                    svg_fragment=fragment,
                    path_count=max(1, 1 + len(region_obj.holes)),
                    simplified=False,
                )
            )
            continue

        base_width = max(int(round(image.shape[1] / coordinate_scale)), 1)
        base_height = max(int(round(image.shape[0] / coordinate_scale)), 1)
        x1, y1, x2, y2 = _clamp_bbox(node.bbox, base_width, base_height)
        crop = _extract_scaled_crop(image, [x1, y1, x2, y2], coordinate_scale)
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


def _render_region_geometry_fragment(component_id: str, region_obj) -> str | None:
    metadata = region_obj.metadata or {}
    fill = region_obj.fill or "none"
    stroke = region_obj.stroke or "#000000"
    fill_opacity = (
        f" fill-opacity='{region_obj.fill_opacity:.3f}'"
        if region_obj.fill_opacity is not None and region_obj.fill_opacity < 0.999
        else ""
    )
    if metadata.get("shape_type") == "circle":
        circle = metadata.get("circle") or {}
        cx = float(circle.get("cx", 0.0))
        cy = float(circle.get("cy", 0.0))
        radius = float(circle.get("r", 0.0))
        return (
            f"<circle id='{component_id}-0' cx='{cx:.1f}' cy='{cy:.1f}' r='{radius:.1f}' "
            f"fill='{fill}' stroke='{stroke}'{fill_opacity} />"
        )
    if metadata.get("shape_type") == "ellipse":
        ellipse = metadata.get("ellipse") or {}
        cx = float(ellipse.get("cx", 0.0))
        cy = float(ellipse.get("cy", 0.0))
        rx = float(ellipse.get("rx", 0.0))
        ry = float(ellipse.get("ry", 0.0))
        rotation = float(ellipse.get("rotation", 0.0))
        transform = "" if abs(rotation) < 0.5 else f" transform='rotate({rotation:.1f} {cx:.1f} {cy:.1f})'"
        return (
            f"<ellipse id='{component_id}-0' cx='{cx:.1f}' cy='{cy:.1f}' rx='{rx:.1f}' ry='{ry:.1f}'"
            f"{transform} fill='{fill}' stroke='{stroke}'{fill_opacity} />"
        )
    return None


def _trace_region_crop(crop: np.ndarray, offset_x: int, offset_y: int, node: SceneNode) -> tuple[str, int]:
    if crop.size == 0:
        return _fallback_region_path(node, offset_x, offset_y, 1, 1), 1

    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        extraction = _extract_region_contours(crop, gray, node)
    except cv2.error:
        height, width = crop.shape[:2]
        return _fallback_region_path(node, offset_x, offset_y, width, height), 1

    if extraction.force_complex_path and extraction.hierarchy is not None:
        fragments = _render_complex_region_paths(extraction, offset_x, offset_y, node)
        if fragments:
            return " ".join(fragments), len(fragments)

    fragments: list[str] = []
    kept = 0
    for contour in sorted(_top_level_contours(extraction), key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < 24:
            continue
        element_id = f"{node.id}-{kept}"
        hint = node.shape_hint if kept == 0 else None
        svg_frag, _ = contour_to_svg_element(
            contour, element_id, offset_x, offset_y,
            fill=node.fill or "none", stroke=node.stroke or "#000000",
            shape_hint=hint,
            fill_opacity=node.fill_opacity,
        )
        fragments.append(svg_frag)
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
    fill_opacity = (
        f" fill-opacity='{node.fill_opacity:.3f}'"
        if node.fill_opacity is not None and node.fill_opacity < 0.999
        else ""
    )
    return (
        f"<path id='{node.id}-fallback' d='M {offset_x} {offset_y} "
        f"L {offset_x + max(width - 1, 1)} {offset_y} "
        f"L {offset_x + max(width - 1, 1)} {offset_y + max(height - 1, 1)} "
        f"L {offset_x} {offset_y + max(height - 1, 1)} Z' "
        f"fill='{node.fill or 'none'}' stroke='{node.stroke or '#000000'}'{fill_opacity} />"
    )


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image


def _extract_scaled_crop(image: np.ndarray, bbox: list[int], coordinate_scale: float) -> np.ndarray:
    source_bbox = _scale_bbox(bbox, coordinate_scale, image.shape[1], image.shape[0])
    x1, y1, x2, y2 = source_bbox
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
    return _clamp_bbox(scaled, width, height)


def _extract_region_contours(crop: np.ndarray, gray: np.ndarray, node: SceneNode) -> _ContourExtractionResult:
    filled_mask = _filled_region_mask(crop, node)
    if filled_mask is not None:
        contours, hierarchy = cv2.findContours(filled_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        useful = [contour for contour in contours if cv2.contourArea(contour) >= 24]
        if useful and hierarchy is not None:
            return _ContourExtractionResult(
                contours=contours,
                hierarchy=hierarchy,
                force_complex_path=_should_force_complex_path(contours, hierarchy, filled_mask.shape[:2]),
            )

    blurred = gaussian_blur(gray, (5, 5), 0)
    edges = canny(blurred, 80, 160)
    _, thresh = threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    combined = cv2.bitwise_or(edges, cv2.bitwise_not(thresh))
    kernel = np.ones((3, 3), np.uint8)
    refined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    contours, hierarchy = cv2.findContours(refined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return _ContourExtractionResult(
        contours=contours,
        hierarchy=hierarchy,
        force_complex_path=hierarchy is not None and _should_force_complex_path(contours, hierarchy, gray.shape[:2]),
    )


def _filled_region_mask(crop: np.ndarray, node: SceneNode) -> np.ndarray | None:
    fill = (node.fill or "").lower()
    if fill in {"", "none", "#ffffff"}:
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


def _top_level_contours(extraction: _ContourExtractionResult) -> list[np.ndarray]:
    if extraction.hierarchy is None:
        return extraction.contours
    return [
        contour
        for idx, contour in enumerate(extraction.contours)
        if extraction.hierarchy[0][idx][3] == -1
    ]


def _should_force_complex_path(
    contours: list[np.ndarray],
    hierarchy: np.ndarray | None,
    image_shape: tuple[int, int],
) -> bool:
    if hierarchy is None:
        return False
    hierarchy_view = hierarchy[0]
    root_indices = select_root_indices(contours, hierarchy_view, image_shape, min_root_area=45.0)
    if len(root_indices) > 1:
        return True
    descendant_count = sum(
        1
        for idx, info in enumerate(hierarchy_view)
        if info[3] != -1 and cv2.contourArea(contours[idx]) >= 20
    )
    if descendant_count >= 1:
        return True
    return False


def _render_complex_region_paths(
    extraction: _ContourExtractionResult,
    offset_x: int,
    offset_y: int,
    node: SceneNode,
) -> list[str]:
    if extraction.hierarchy is None:
        return []
    hierarchy = extraction.hierarchy[0]
    root_indices = select_root_indices(extraction.contours, hierarchy, _contour_canvas_shape(extraction.contours), min_root_area=45.0)
    if not root_indices:
        root_indices = [
            idx for idx, info in enumerate(hierarchy)
            if info[3] == -1 and cv2.contourArea(extraction.contours[idx]) >= 24
        ]
    fragments: list[str] = []
    kept = 0
    for root_idx in root_indices:
        if cv2.contourArea(extraction.contours[root_idx]) < 24:
            continue
        commands = collect_compound_subpaths(
            extraction.contours,
            hierarchy,
            [root_idx],
            offset_x=offset_x,
            offset_y=offset_y,
            min_area=20.0,
            min_epsilon=1.5,
        )
        if not commands:
            continue
        if len(commands) == 1:
            svg_frag, _ = contour_to_svg_element(
                extraction.contours[root_idx],
                f"{node.id}-{kept}",
                offset_x,
                offset_y,
                fill=node.fill or "none",
                stroke=node.stroke or "#000000",
                shape_hint=node.shape_hint if kept == 0 else None,
                fill_opacity=node.fill_opacity,
            )
            fragments.append(svg_frag)
            kept += 1
            continue
        fill_attr = (
            f" fill-opacity='{node.fill_opacity:.3f}'"
            if node.fill_opacity is not None and node.fill_opacity < 0.999
            else ""
        )
        fragments.append(
            f"<path id='{node.id}-{kept}' d='{' '.join(commands)}' "
            f"fill='{node.fill or 'none'}' stroke='{node.stroke or '#000000'}'"
            f"{fill_attr} fill-rule='evenodd' />"
        )
        kept += 1
    return fragments


def _contour_canvas_shape(contours: list[np.ndarray]) -> tuple[int, int]:
    max_x = 1
    max_y = 1
    for contour in contours:
        if contour.size == 0:
            continue
        max_x = max(max_x, int(np.max(contour[:, 0, 0])) + 1)
        max_y = max(max_y, int(np.max(contour[:, 0, 1])) + 1)
    return max_y, max_x


def _contour_path_commands(contour: np.ndarray, offset_x: int, offset_y: int) -> str:
    return contour_path_commands(contour, offset_x, offset_y, min_epsilon=1.5)
