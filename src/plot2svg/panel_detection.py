"""Panel detection helpers extracted from the pipeline orchestration module."""

from __future__ import annotations

import cv2
import numpy as np

from .bbox_utils import _bbox_overlap, _clamp_bbox
from .color_utils import _hex_to_bgr, _is_near_white, _sample_arrow_fill_color, _sample_panel_border_color, _sample_panel_fill
from .scene_graph import RegionObject, SceneGraph, SceneNode


def _inject_panel_background_regions(
    source_image: np.ndarray,
    scene_graph: SceneGraph,
    text_nodes: list[SceneNode],
) -> SceneGraph:
    """Detect and attach synthetic panel background nodes to a scene graph.

    Args:
        source_image: Source BGR image.
        scene_graph: Scene graph to augment.
        text_nodes: Visible text nodes used to infer panel columns.

    Returns:
        A scene graph with synthetic panel regions injected when detected.
    """
    panel_nodes = _detect_panel_background_nodes(
        source_image,
        text_nodes,
        scene_graph.width,
        scene_graph.height,
        existing_nodes=scene_graph.nodes,
    )
    return _attach_panel_background_regions(scene_graph, panel_nodes)


def _detect_panel_background_nodes(
    source_image: np.ndarray,
    text_nodes: list[SceneNode],
    width: int,
    height: int,
    existing_nodes: list[SceneNode] | None = None,
) -> list[SceneNode]:
    """Detect large panel-like background regions from text column structure.

    Args:
        source_image: Source BGR image.
        text_nodes: Visible text nodes.
        width: Canvas width.
        height: Canvas height.
        existing_nodes: Existing graph nodes used to avoid duplicate panels.

    Returns:
        Synthetic panel region nodes when a panel layout is detected.
    """
    existing_nodes = existing_nodes or []
    if any(node.id.startswith("panel-region-") for node in existing_nodes):
        return []

    canvas_area = max(width * height, 1)
    existing_large_regions = [
        node
        for node in existing_nodes
        if node.type == "region"
        and node.id != "background-root"
        and (node.bbox[2] - node.bbox[0]) * (node.bbox[3] - node.bbox[1]) >= canvas_area * 0.05
    ]
    if len(existing_large_regions) >= 2:
        return []

    column_groups = _cluster_text_columns(text_nodes, width)
    if len(column_groups) < 3:
        return []

    boundaries = [0]
    for left_group, right_group in zip(column_groups, column_groups[1:]):
        boundaries.append(int(round((left_group[1] + right_group[0]) / 2.0)))
    boundaries.append(width)

    visible_text = [node for node in text_nodes if (node.text_content or "").strip()]
    if not visible_text:
        return []
    top = max(min(node.bbox[1] for node in visible_text) - 28, 0)
    bottom = min(max(node.bbox[3] for node in visible_text) + 28, height)
    if (bottom - top) * width < canvas_area * 0.2:
        return []

    blurred = cv2.GaussianBlur(source_image, (101, 101), 0)
    panel_nodes: list[SceneNode] = []
    for index, (x1, x2) in enumerate(zip(boundaries, boundaries[1:])):
        bbox = [max(x1, 0), top, min(x2, width), bottom]
        if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < canvas_area * 0.05:
            continue
        fill = _sample_panel_fill(blurred, bbox)
        if fill is None or _is_near_white(fill):
            continue
        panel_nodes.append(
            SceneNode(
                id=f"panel-region-{index:03d}",
                type="region",
                bbox=bbox,
                z_index=index + 1,
                vector_mode="region_path",
                confidence=0.99,
                fill=fill,
                fill_opacity=0.92,
                stroke=fill,
                shape_hint="panel",
            )
        )
    if len(panel_nodes) < 3:
        return []
    return panel_nodes


def _attach_panel_background_regions(
    scene_graph: SceneGraph,
    panel_nodes: list[SceneNode],
) -> SceneGraph:
    """Insert detected panel nodes ahead of the normal region body nodes.

    Args:
        scene_graph: Scene graph to augment.
        panel_nodes: Synthetic panel nodes to insert.

    Returns:
        A scene graph with panel nodes inserted in stable z-order.
    """
    if not panel_nodes:
        return scene_graph
    if any(node.id.startswith("panel-region-") for node in scene_graph.nodes):
        return scene_graph

    background_nodes = [node for node in scene_graph.nodes if node.id == "background-root"]
    other_nodes = [node for node in scene_graph.nodes if node.id != "background-root"]
    reordered_nodes: list[SceneNode] = []
    for index, node in enumerate([*background_nodes, *panel_nodes, *other_nodes]):
        reordered_nodes.append(
            SceneNode(
                id=node.id,
                type=node.type,
                bbox=node.bbox[:],
                z_index=index,
                vector_mode=node.vector_mode,
                confidence=node.confidence,
                fill=node.fill,
                fill_opacity=node.fill_opacity,
                stroke=node.stroke,
                stroke_width=node.stroke_width,
                source_mask=node.source_mask,
                text_content=node.text_content,
                group_id=node.group_id,
                component_role=node.component_role,
                children=node.children[:],
                shape_hint=node.shape_hint,
            )
        )

    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=reordered_nodes,
        groups=scene_graph.groups[:],
        relations=scene_graph.relations[:],
        objects=scene_graph.objects[:],
        stroke_primitives=scene_graph.stroke_primitives[:],
        node_objects=scene_graph.node_objects[:],
        region_objects=scene_graph.region_objects[:],
        icon_objects=scene_graph.icon_objects[:],
        raster_objects=scene_graph.raster_objects[:],
        graph_edges=scene_graph.graph_edges[:],
    )


def _detect_panel_arrow_regions(
    source_image: np.ndarray,
    working_image: np.ndarray,
    panel_nodes: list[SceneNode],
) -> tuple[list[SceneNode], list[RegionObject]]:
    """Detect synthetic right-pointing arrows that connect adjacent panels.

    Args:
        source_image: Source BGR image.
        working_image: Current working image after panel cleanup.
        panel_nodes: Detected panel nodes.

    Returns:
        Synthetic panel arrow nodes plus matching region objects.
    """
    ordered_panels = sorted(panel_nodes, key=lambda item: item.bbox[0])
    if len(ordered_panels) < 2:
        return [], []

    visible_boxes = [_estimate_visible_panel_bbox(source_image, node) for node in ordered_panels]
    border_colors = [_sample_panel_border_color(source_image, bbox) for bbox in visible_boxes[:-1]]
    border_mask = np.zeros(working_image.shape[:2], dtype=np.uint8)
    for x1, y1, x2, y2 in visible_boxes:
        cv2.rectangle(border_mask, (x1, y1), (x2 - 1, y2 - 1), 255, 8)

    hsv = cv2.cvtColor(working_image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(working_image, cv2.COLOR_BGR2GRAY)
    base_mask = np.where((hsv[:, :, 1] > 35) & (gray < 220) & (border_mask == 0), 255, 0).astype(np.uint8)
    base_mask = cv2.morphologyEx(base_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    base_mask = cv2.morphologyEx(base_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    arrow_nodes: list[SceneNode] = []
    arrow_objects: list[RegionObject] = []
    image_height, image_width = working_image.shape[:2]
    for index, (left_box, right_box, border_color) in enumerate(zip(visible_boxes, visible_boxes[1:], border_colors)):
        if border_color is None:
            continue
        boundary = left_box[2]
        search_x1 = max(boundary - 80, 0)
        search_x2 = min(boundary + 80, image_width)
        search_y1 = max(min(left_box[1], right_box[1]) + 120, 0)
        search_y2 = min(int(image_height * 0.60), image_height)
        if search_y2 <= search_y1:
            continue
        crop = base_mask[search_y1:search_y2, search_x1:search_x2]
        if crop.size == 0:
            continue

        candidate_boxes = _collect_boundary_arrow_boxes(crop, boundary, search_x1, search_y1)
        selected_boxes = _select_boundary_arrow_boxes(candidate_boxes, boundary)
        for local_index, bbox in enumerate(selected_boxes):
            fill = _sample_arrow_fill_color(source_image, bbox, border_color)
            node_bbox, path = _synthesize_right_arrow_path(bbox, right_box[0])
            node_id = f"panel-arrow-region-{index:02d}-{local_index:02d}"
            arrow_nodes.append(
                SceneNode(
                    id=node_id,
                    type="region",
                    bbox=node_bbox,
                    z_index=0,
                    vector_mode="region_path",
                    confidence=0.96,
                    fill=fill,
                    fill_opacity=0.98,
                    stroke=fill,
                    shape_hint="panel_arrow",
                )
            )
            arrow_objects.append(
                RegionObject(
                    id=f"region-object-{node_id}",
                    node_id=node_id,
                    outer_path=path,
                    holes=[],
                    fill=fill,
                    fill_opacity=0.98,
                    stroke=fill,
                    metadata={
                        "shape_type": "panel_arrow_template",
                        "synthetic": True,
                        "orientation": "right",
                        "template_bbox": node_bbox,
                    },
                )
            )
    return arrow_nodes, arrow_objects


def _estimate_visible_panel_bbox(source_image: np.ndarray, node: SceneNode) -> list[int]:
    """Estimate the visible bbox of a panel from its fill color footprint.

    Args:
        source_image: Source BGR image.
        node: Synthetic panel node.

    Returns:
        A refined bbox for the visible panel body.
    """
    target_bgr = _hex_to_bgr(node.fill)
    if target_bgr is None:
        return node.bbox[:]
    x1, y1, x2, y2 = _clamp_bbox(node.bbox, source_image.shape[1], source_image.shape[0])
    crop = source_image[y1:y2, x1:x2].astype(np.int16)
    if crop.size == 0:
        return node.bbox[:]
    gray = cv2.cvtColor(source_image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    delta = np.max(np.abs(crop - np.array(target_bgr, dtype=np.int16)), axis=2)
    mask = np.where((delta <= 24) & (gray >= 170), 255, 0).astype(np.uint8)
    points = cv2.findNonZero(mask)
    if points is None:
        return node.bbox[:]
    rx, ry, width, height = cv2.boundingRect(points)
    return [x1 + int(rx), y1 + int(ry), x1 + int(rx + width), y1 + int(ry + height)]


def _collect_boundary_arrow_boxes(
    crop_mask: np.ndarray,
    boundary: int,
    offset_x: int,
    offset_y: int,
) -> list[list[int]]:
    """Collect candidate arrow boxes near a panel boundary from a mask crop.

    Args:
        crop_mask: Binary candidate mask in the search window.
        boundary: X position of the panel boundary.
        offset_x: X offset from crop to image coordinates.
        offset_y: Y offset from crop to image coordinates.

    Returns:
        Candidate global bounding boxes merged for near-duplicates.
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(crop_mask, connectivity=8)
    boxes: list[list[int]] = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area < 100:
            continue
        global_bbox = [offset_x + int(x), offset_y + int(y), offset_x + int(x + width), offset_y + int(y + height)]
        if global_bbox[2] < boundary - 25 or global_bbox[0] > boundary + 70:
            continue
        if width > 120 or height > 120:
            continue
        boxes.append(global_bbox)
    return _merge_nearby_bboxes(boxes)


def _merge_nearby_bboxes(boxes: list[list[int]]) -> list[list[int]]:
    """Merge close arrow candidate boxes into larger candidates.

    Args:
        boxes: Candidate boxes in xyxy format.

    Returns:
        Merged candidate boxes.
    """
    merged = [box[:] for box in boxes]
    changed = True
    while changed:
        changed = False
        next_boxes: list[list[int]] = []
        while merged:
            current = merged.pop(0)
            merged_current = False
            for index, other in enumerate(merged):
                vertical_overlap = min(current[3], other[3]) - max(current[1], other[1])
                horizontal_gap = max(other[0] - current[2], current[0] - other[2], 0)
                if vertical_overlap >= min(current[3] - current[1], other[3] - other[1]) * 0.4 and horizontal_gap <= 18:
                    current = [
                        min(current[0], other[0]),
                        min(current[1], other[1]),
                        max(current[2], other[2]),
                        max(current[3], other[3]),
                    ]
                    merged.pop(index)
                    changed = True
                    merged_current = True
                    break
            if merged_current:
                merged.insert(0, current)
                continue
            next_boxes.append(current)
        merged = next_boxes
    return merged


def _select_boundary_arrow_boxes(boxes: list[list[int]], boundary: int) -> list[list[int]]:
    """Pick the best boundary-arrow candidates from collected boxes.

    Args:
        boxes: Candidate boxes in xyxy format.
        boundary: X position of the panel boundary.

    Returns:
        A filtered list of selected candidate boxes.
    """
    if not boxes:
        return []
    ranked = sorted(boxes, key=lambda item: ((item[2] - item[0]) * (item[3] - item[1])), reverse=True)
    selected: list[list[int]] = []
    wide_candidate = next(
        (
            box for box in ranked
            if (box[2] - box[0]) >= 28 and (box[3] - box[1]) <= 48 and box[1] <= 260
        ),
        None,
    )
    if wide_candidate is not None:
        selected.append(wide_candidate)
    tall_candidate = next(
        (
            box for box in ranked
            if (box[3] - box[1]) >= 30 and (box[2] - box[0]) <= 24 and box[0] <= boundary + 24
        ),
        None,
    )
    if tall_candidate is not None and all(_bbox_overlap(tall_candidate, current) < 0.3 for current in selected):
        selected.append(tall_candidate)
    if not selected and ranked:
        selected.append(ranked[0])
    return selected


def _synthesize_right_arrow_path(bbox: list[int], next_panel_left: int) -> tuple[list[int], str]:
    """Build a simple right-pointing synthetic arrow path from a bbox.

    Args:
        bbox: Arrow body bbox in xyxy format.
        next_panel_left: Left edge of the next panel.

    Returns:
        The expanded arrow bbox plus a closed SVG path.
    """
    x1, y1, x2, y2 = bbox
    height = max(y2 - y1, 1)
    width = max(x2 - x1, 1)
    head_width = max(min(int(height * 0.9), 40), 16)
    if width >= 28:
        body_x2 = x2
        tip_x = min(x2 + max(head_width // 2, 10), next_panel_left + 42)
    else:
        body_x2 = x2
        tip_x = min(x2 + head_width, next_panel_left + 42)
    mid_y = (y1 + y2) // 2
    path = (
        f"M {x1} {y1} "
        f"L {body_x2} {y1} "
        f"L {tip_x} {mid_y} "
        f"L {body_x2} {y2} "
        f"L {x1} {y2} Z"
    )
    return [x1, y1, tip_x, y2], path


def _cluster_text_columns(text_nodes: list[SceneNode], width: int) -> list[tuple[int, int]]:
    """Cluster text boxes into coarse horizontal columns.

    Args:
        text_nodes: Visible text nodes.
        width: Canvas width.

    Returns:
        Column spans in x coordinates.
    """
    intervals = sorted(
        [
            (node.bbox[0], node.bbox[2])
            for node in text_nodes
            if (node.text_content or "").strip()
        ],
        key=lambda item: item[0],
    )
    if not intervals:
        return []

    gap_threshold = max(24, int(width * 0.015))
    clusters: list[list[int]] = []
    for x1, x2 in intervals:
        if not clusters or x1 > clusters[-1][1] + gap_threshold:
            clusters.append([x1, x2])
        else:
            clusters[-1][1] = max(clusters[-1][1], x2)
    return [(x1, x2) for x1, x2 in clusters if (x2 - x1) >= max(60, int(width * 0.08))]
