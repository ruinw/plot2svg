"""Inpaint helpers extracted from the pipeline orchestration module."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .image_io import read_image
from .scene_graph import SceneGraph, SceneNode


def _mask_ignored_regions(image: np.ndarray, ignore_mask: np.ndarray) -> np.ndarray:
    """Return a copy of the image with ignored pixels whitened.

    Args:
        image: Source BGR image.
        ignore_mask: Binary mask marking pixels to erase.

    Returns:
        A copied image with ignored pixels set to white.
    """
    if ignore_mask.size == 0 or not np.any(ignore_mask):
        return image.copy()
    cleaned = image.copy()
    cleaned[ignore_mask > 0] = 255
    return cleaned


def _heal_masked_stage_image(
    image: np.ndarray,
    ignore_mask: np.ndarray,
    kernel_size: int = 7,
) -> np.ndarray:
    """Heal masked regions using dominant colors sampled from a ring.

    Args:
        image: Source BGR image.
        ignore_mask: Binary mask marking pixels to heal.
        kernel_size: Morphology kernel size used during cleanup.

    Returns:
        A healed image copy.
    """
    cleaned = _mask_ignored_regions(image, ignore_mask)
    if ignore_mask.size == 0 or not np.any(ignore_mask):
        return cleaned

    kernel_size = max(kernel_size | 1, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    healed = cleaned.copy()

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.where(ignore_mask > 0, 255, 0).astype(np.uint8),
        connectivity=8,
    )
    for label in range(1, num_labels):
        _x, _y, _width, _height, area = stats[label]
        if area <= 0:
            continue

        component_mask = np.where(labels == label, 255, 0).astype(np.uint8)
        ring_mask = cv2.dilate(component_mask, kernel, iterations=1)
        ring_mask = cv2.subtract(ring_mask, component_mask)
        ring_pixels = image[ring_mask > 0]
        if ring_pixels.size == 0:
            continue

        quantized = np.clip(((ring_pixels.astype(np.int32) + 8) // 16) * 16, 0, 255)
        colors, counts = np.unique(quantized, axis=0, return_counts=True)
        dominant_quantized = colors[int(np.argmax(counts))]
        dominant_pixels = ring_pixels[np.all(quantized == dominant_quantized, axis=1)]
        dominant = np.median(dominant_pixels, axis=0).astype(np.uint8)
        healed[component_mask > 0] = dominant

    closed = cv2.morphologyEx(healed, cv2.MORPH_CLOSE, kernel)
    expanded_mask = cv2.dilate(ignore_mask, kernel, iterations=1)
    healed[expanded_mask > 0] = closed[expanded_mask > 0]
    return healed


def _mask_for_nodes(
    image: np.ndarray,
    nodes: list[SceneNode],
    padding: int = 0,
    artifacts_dir: Path | None = None,
) -> np.ndarray:
    """Build a union mask for the provided scene nodes.

    Args:
        image: Source BGR image.
        nodes: Nodes whose areas should be masked.
        padding: Optional dilation padding.
        artifacts_dir: Directory used to resolve saved component masks.

    Returns:
        A binary mask covering the requested nodes.
    """
    if not nodes:
        return np.zeros(image.shape[:2], dtype=np.uint8)

    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    for node in nodes:
        if node.shape_hint == "panel" and node.fill:
            node_mask = _panel_background_mask(image, node)
            if node_mask is None:
                node_mask = _bbox_mask(node.bbox, width, height)
        else:
            node_mask = _rasterize_node_mask(node, width, height, artifacts_dir)
            if node_mask is None:
                node_mask = _bbox_mask(node.bbox, width, height)
        mask = cv2.bitwise_or(mask, node_mask)

    if padding > 0 and np.any(mask):
        kernel_size = max((padding * 2) + 1, 3)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def _inpaint_node_and_icon_regions(
    image: np.ndarray,
    scene_graph: SceneGraph,
    node_ids: set[str],
    padding: int,
    artifacts_dir: Path | None = None,
    existing_ignore_mask: np.ndarray | None = None,
    kernel_size: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    """Inpaint node and icon regions selected by explicit node ids.

    Args:
        image: Source BGR image.
        scene_graph: Graph containing candidate nodes.
        node_ids: Node ids that should be removed.
        padding: Optional dilation padding.
        artifacts_dir: Directory used to resolve saved component masks.
        existing_ignore_mask: Existing accumulated ignore mask.
        kernel_size: Morphology kernel size used during cleanup.

    Returns:
        The healed image and the newly created node mask.
    """
    mask = _build_inpaint_mask(
        image,
        scene_graph,
        lambda node: node.id in node_ids,
        padding=padding,
        artifacts_dir=artifacts_dir,
    )
    combined_mask = _merge_masks(existing_ignore_mask, mask)
    return _heal_masked_stage_image(image, combined_mask, kernel_size=kernel_size), mask


def _is_exportable_stroke_node(node: SceneNode, scene_graph: SceneGraph) -> bool:
    """Return whether a stroke node is small enough to be treated as a stroke.

    Args:
        node: Candidate stroke node.
        scene_graph: Scene graph used to normalize area ratios.

    Returns:
        True when the stroke should remain in the stroke layer.
    """
    x1, y1, x2, y2 = node.bbox
    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    area = width * height
    canvas_area = max(scene_graph.width * scene_graph.height, 1)
    width_ratio = width / max(scene_graph.width, 1)
    height_ratio = height / max(scene_graph.height, 1)
    if area >= canvas_area * 0.25:
        return False
    if width_ratio >= 0.85 and height_ratio >= 0.50:
        return False
    if height_ratio >= 0.85 and width_ratio >= 0.50:
        return False
    return True


def _inpaint_stroke_regions(
    image: np.ndarray,
    scene_graph: SceneGraph,
    padding: int,
    artifacts_dir: Path | None = None,
    existing_ignore_mask: np.ndarray | None = None,
    kernel_size: int = 7,
) -> tuple[np.ndarray, np.ndarray]:
    """Inpaint stroke regions while preserving oversized stroke clusters.

    Args:
        image: Source BGR image.
        scene_graph: Graph containing candidate stroke nodes.
        padding: Optional dilation padding.
        artifacts_dir: Directory used to resolve saved component masks.
        existing_ignore_mask: Existing accumulated ignore mask.
        kernel_size: Morphology kernel size used during cleanup.

    Returns:
        The healed image and the newly created stroke mask.
    """
    mask = _build_inpaint_mask(
        image,
        scene_graph,
        lambda node: node.type == "stroke" and _should_inpaint_stroke_node(node, scene_graph),
        padding=padding,
        artifacts_dir=artifacts_dir,
    )
    combined_mask = _merge_masks(existing_ignore_mask, mask)
    return _heal_masked_stage_image(image, combined_mask, kernel_size=kernel_size), mask


def _erase_region_nodes(
    image: np.ndarray,
    nodes: list[SceneNode],
    padding: int = 0,
) -> np.ndarray:
    """Whiten the provided region nodes without healing surrounding pixels.

    Args:
        image: Source BGR image.
        nodes: Nodes whose pixels should be whitened.
        padding: Optional dilation padding.

    Returns:
        A copied image with the requested region pixels whitened.
    """
    mask = _mask_for_nodes(image, nodes, padding=padding, artifacts_dir=None)
    return _mask_ignored_regions(image, mask)


def _panel_background_mask(image: np.ndarray, node: SceneNode) -> np.ndarray | None:
    """Rasterize a panel mask by sampling pixels close to the panel fill color.

    Args:
        image: Source BGR image.
        node: Panel scene node.

    Returns:
        A mask for pixels matching the panel background, or None.
    """
    target_bgr = _hex_to_bgr(node.fill)
    if target_bgr is None:
        return None
    height, width = image.shape[:2]
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, width, height)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    color_delta = np.max(np.abs(crop.astype(np.int16) - np.array(target_bgr, dtype=np.int16)), axis=2)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    local_mask = np.where((color_delta <= 32) & (gray >= 170), 255, 0).astype(np.uint8)
    if not np.any(local_mask):
        return None
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = local_mask
    return full_mask


def _should_inpaint_stroke_node(node: SceneNode, scene_graph: SceneGraph) -> bool:
    """Return whether a stroke node should be removed before region vectorization.

    Args:
        node: Candidate stroke node.
        scene_graph: Scene graph used to normalize area ratios.

    Returns:
        True when the stroke should be inpainted.
    """
    return _is_exportable_stroke_node(node, scene_graph)


def _build_inpaint_mask(
    image: np.ndarray,
    scene_graph: SceneGraph,
    predicate: Callable[[SceneNode], bool],
    *,
    padding: int,
    artifacts_dir: Path | None,
) -> np.ndarray:
    """Build an inpaint mask from graph nodes selected by a predicate.

    Args:
        image: Source BGR image.
        scene_graph: Graph containing candidate nodes.
        predicate: Predicate deciding which nodes to include.
        padding: Optional dilation padding.
        artifacts_dir: Directory used to resolve saved component masks.

    Returns:
        A binary mask covering the selected nodes.
    """
    selected_nodes = [node for node in scene_graph.nodes if predicate(node)]
    return _mask_for_nodes(image, selected_nodes, padding=padding, artifacts_dir=artifacts_dir)


def _rasterize_node_mask(
    node: SceneNode,
    width: int,
    height: int,
    artifacts_dir: Path | None,
) -> np.ndarray | None:
    """Rasterize a node mask from its stored component mask when available.

    Args:
        node: Scene node whose source mask should be restored.
        width: Output canvas width.
        height: Output canvas height.
        artifacts_dir: Directory used to resolve saved component masks.

    Returns:
        A full-size binary mask, or None when no source mask is available.
    """
    if artifacts_dir is None or not node.source_mask:
        return None
    mask_path = artifacts_dir / node.source_mask
    if not mask_path.exists():
        return None
    local_mask = read_image(mask_path, cv2.IMREAD_GRAYSCALE)
    if local_mask is None:
        return None
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, width, height)
    target_w = max(x2 - x1, 1)
    target_h = max(y2 - y1, 1)
    if local_mask.shape[1] != target_w or local_mask.shape[0] != target_h:
        local_mask = cv2.resize(local_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    full_mask = np.zeros((height, width), dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = np.where(local_mask > 0, 255, 0).astype(np.uint8)
    return full_mask


def _bbox_mask(bbox: list[int], width: int, height: int) -> np.ndarray:
    """Return a rectangular mask covering the provided bounding box.

    Args:
        bbox: Bounding box in xyxy format.
        width: Output canvas width.
        height: Output canvas height.

    Returns:
        A binary mask for the bounding box area.
    """
    mask = np.zeros((height, width), dtype=np.uint8)
    x1, y1, x2, y2 = _clamp_bbox(bbox, width, height)
    mask[y1:y2, x1:x2] = 255
    return mask


def _merge_masks(*masks: np.ndarray | None) -> np.ndarray:
    """Merge multiple binary masks into a single binary mask.

    Args:
        *masks: Optional masks to merge.

    Returns:
        The merged binary mask.
    """
    available = [mask for mask in masks if mask is not None and mask.size > 0]
    if not available:
        return np.zeros((0, 0), dtype=np.uint8)

    merged = np.zeros_like(available[0], dtype=np.uint8)
    for mask in available:
        merged = cv2.bitwise_or(merged, np.where(mask > 0, 255, 0).astype(np.uint8))
    return merged


def _hex_to_bgr(color: str | None) -> tuple[int, int, int] | None:
    """Convert a CSS hex color string to a BGR tuple.

    Args:
        color: Color string such as ``#aabbcc``.

    Returns:
        A BGR tuple, or None when the input is invalid.
    """
    if color is None or not color.startswith("#") or len(color) != 7:
        return None
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return None
    return b, g, r


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    """Clamp a bbox to image bounds while keeping a non-zero area.

    Args:
        bbox: Bounding box in xyxy format.
        width: Image width.
        height: Image height.

    Returns:
        The clamped bounding box.
    """
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2
