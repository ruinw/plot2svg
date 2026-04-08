"""Component proposal generation for Plot2SVG."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from .image_io import read_image, write_image

from .config import PipelineConfig
from .detect_shapes import SHAPE_CIRCLE, SHAPE_POLYGON, SHAPE_TRIANGLE, classify_contour
from .gpu import gaussian_blur, resize, threshold

ImageInput = Union[Path, np.ndarray]

_RASTER_CANDIDATE_HINT = 'raster_candidate'

@dataclass(slots=True)
class _ProposalRecord:
    bbox: list[int]
    proposal_type: str
    confidence: float
    mask: np.ndarray
    shape_hint: str | None = None


@dataclass(slots=True)
class ComponentProposal:
    """A raw component proposal extracted from an image."""

    component_id: str
    bbox: list[int]
    mask_path: str
    proposal_type: str
    confidence: float
    shape_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def propose_components(
    image_input: ImageInput,
    output_dir: Path,
    cfg: PipelineConfig | None = None,
    text_image_input: ImageInput | None = None,
) -> list[ComponentProposal]:
    """Generate mask proposals from an image using contour extraction."""

    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)

    image = _load_color_image(image_input)
    text_image = image if text_image_input is None else _load_color_image(text_image_input)

    original_height, original_width = image.shape[:2]
    resize_scale = get_proposal_resize_scale(original_width, original_height, cfg)
    working_image = image
    if resize_scale < 1.0:
        working_image = resize(
            image,
            (max(int(original_width * resize_scale), 1), max(int(original_height * resize_scale), 1)),
            interpolation=cv2.INTER_AREA,
        )

    records = _extract_records(working_image, resize_scale=resize_scale, text_only=False, min_area=20)
    records.extend(_extract_records(text_image, resize_scale=1.0, text_only=True, min_area=10))

    records = _compress_records(records, original_width, original_height)
    records = _cluster_icon_candidate_records(records, original_width, original_height)
    proposals = _records_to_component_proposals(records, masks_dir)
    proposals = compress_proposals(proposals, original_width, original_height)
    proposals = _limit_text_like_proposals(proposals, original_width, original_height)
    if cfg is None or cfg.enable_shape_detection:
        proposals = _inject_hough_circles(image, proposals, masks_dir, original_width, original_height, cfg)
    proposals = _ensure_mixed_component_types(proposals, original_width, original_height, masks_dir)
    _write_region_segmentation_debug(output_dir / "debug_region_segmentation.png", proposals, masks_dir, original_width, original_height)
    _write_components_json(output_dir / "components_raw.json", proposals)
    return proposals


def get_proposal_resize_scale(image_width: int, image_height: int, cfg: PipelineConfig | None = None) -> float:
    """Return the scale used for connected-component proposal generation."""

    max_side_limit = resolve_proposal_max_side(cfg)
    max_side = max(image_width, image_height)
    if max_side <= max_side_limit:
        return 1.0
    return min(max_side_limit / max_side, 1.0)


def resolve_proposal_max_side(cfg: PipelineConfig | None) -> int:
    if cfg is None:
        return 1800
    return cfg.proposal_max_side()


def _extract_records(
    image: np.ndarray,
    *,
    resize_scale: float,
    text_only: bool,
    min_area: int,
) -> list[_ProposalRecord]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_kernel = (3, 3) if text_only else (5, 5)
    blurred = gaussian_blur(gray, blur_kernel, 0)
    if text_only:
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            11,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
        refined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    else:
        _, binary = threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = np.ones((3, 3), np.uint8)
        refined = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        refined = cv2.morphologyEx(refined, cv2.MORPH_CLOSE, kernel)

    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(refined, connectivity=8)
    records: list[_ProposalRecord] = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area < min_area:
            continue
        proposal_type = "text_like" if text_only else classify_component_role(width, height, area)
        component_mask = np.where(labels == label, 255, 0).astype(np.uint8)
        component_masks = [component_mask]
        if not text_only and proposal_type == "region":
            component_masks = _split_component_mask(component_mask)
        for part_mask in component_masks:
            detail_masks = [part_mask]
            detail_hint = None
            if not text_only and proposal_type == "region":
                dense_parts = _split_dense_detail_cluster(part_mask)
                if len(dense_parts) > 1:
                    detail_masks = dense_parts
                    detail_hint = 'dense_detail'
            for detail_mask in detail_masks:
                part_area = int(np.count_nonzero(detail_mask))
                if part_area < min_area:
                    continue
                bbox = _mask_bbox(detail_mask)
                if bbox is None:
                    continue
                part_type = proposal_type
                if not text_only and part_type == "region" and _looks_like_dense_stroke_cluster(detail_mask):
                    part_type = "stroke"
                shape_hint = _infer_shape_hint(detail_mask) or detail_hint
                if not text_only and part_type == "region" and shape_hint != 'dense_detail' and _is_complex_raster_candidate(image, detail_mask):
                    shape_hint = _RASTER_CANDIDATE_HINT
                confidence = min(0.5 + (part_area / max(_bbox_area(bbox), 1)), 0.99)
                records.append(
                    _ProposalRecord(
                        bbox=_scale_bbox_back(bbox, resize_scale),
                        proposal_type=part_type,
                        confidence=float(confidence),
                        mask=detail_mask,
                        shape_hint=shape_hint,
                    )
                )
    return records


def compress_proposals(
    proposals: list[ComponentProposal],
    image_width: int,
    image_height: int,
) -> list[ComponentProposal]:
    """Filter tiny fragments and merge highly overlapping proposals."""

    image_area = max(image_width * image_height, 1)
    filtered: list[ComponentProposal] = []
    for proposal in proposals:
        area = _bbox_area(proposal.bbox)
        min_area = _min_component_area(proposal.proposal_type, image_area)
        if area < min_area:
            continue
        filtered.append(proposal)

    merged: list[ComponentProposal] = []
    for proposal in sorted(filtered, key=lambda item: _bbox_area(item.bbox), reverse=True):
        match_index = _find_merge_target(merged, proposal)
        if match_index is None:
            merged.append(proposal)
            continue
        merged[match_index] = _merge_two_proposals(merged[match_index], proposal)

    return sorted(merged, key=lambda item: (item.proposal_type, item.bbox[1], item.bbox[0]))


def classify_component_role(width: int, height: int, area: int) -> str:
    bbox_area = max(width * height, 1)
    fill_ratio = area / bbox_area
    aspect_ratio = max(width, 1) / max(height, 1)
    if height <= 28 and width >= 32 and fill_ratio > 0.28 and aspect_ratio >= 1.8:
        return "text_like"
    if fill_ratio < 0.28 or min(width, height) < 14:
        return "stroke"
    return "region"


def _min_component_area(proposal_type: str, image_area: int) -> int:
    if proposal_type == "stroke":
        return max(32, int(image_area * 0.000045))
    if proposal_type == "text_like":
        return max(64, int(image_area * 0.00007))
    return max(96, int(image_area * 0.00018))


def _find_merge_target(existing: list[ComponentProposal], incoming: ComponentProposal) -> int | None:
    for index, current in enumerate(existing):
        if current.proposal_type != incoming.proposal_type:
            continue
        if _should_merge_records(current.bbox, incoming.bbox, current.shape_hint, incoming.shape_hint):
            return index
    return None


def _merge_two_proposals(left: ComponentProposal, right: ComponentProposal) -> ComponentProposal:
    x1 = min(left.bbox[0], right.bbox[0])
    y1 = min(left.bbox[1], right.bbox[1])
    x2 = max(left.bbox[2], right.bbox[2])
    y2 = max(left.bbox[3], right.bbox[3])
    return ComponentProposal(
        component_id=left.component_id,
        bbox=[x1, y1, x2, y2],
        mask_path=left.mask_path,
        proposal_type=left.proposal_type,
        confidence=max(left.confidence, right.confidence),
        shape_hint=left.shape_hint or right.shape_hint,
    )

def _bbox_area(bbox: list[int]) -> int:
    return max(bbox[2] - bbox[0], 1) * max(bbox[3] - bbox[1], 1)


def _overlap_ratio(left: list[int], right: list[int]) -> float:
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    return intersection / max(min(_bbox_area(left), _bbox_area(right)), 1)


def _should_merge_records(
    left_bbox: list[int],
    right_bbox: list[int],
    left_shape_hint: str | None,
    right_shape_hint: str | None,
) -> bool:
    if left_shape_hint == 'dense_detail' or right_shape_hint == 'dense_detail':
        return False
    overlap = _overlap_ratio(left_bbox, right_bbox)
    if _is_explicit_geometric_hint(left_shape_hint) or _is_explicit_geometric_hint(right_shape_hint):
        if left_shape_hint and right_shape_hint and left_shape_hint != right_shape_hint:
            return False
        return overlap >= 0.94
    return overlap >= 0.82


def _is_explicit_geometric_hint(shape_hint: str | None) -> bool:
    return shape_hint in {"circle", "triangle", "pentagon"}


def _mask_bbox(mask: np.ndarray) -> list[int] | None:
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    return [int(x), int(y), int(x + width), int(y + height)]


def _split_component_mask(mask: np.ndarray) -> list[np.ndarray]:
    bbox = _mask_bbox(mask)
    if bbox is None:
        return []
    x1, y1, x2, y2 = bbox
    crop = mask[y1:y2, x1:x2]
    area = int(np.count_nonzero(crop))
    width = x2 - x1
    height = y2 - y1
    if area < 400 or width < 28 or height < 28:
        return [mask]
    fill_ratio = area / max(width * height, 1)
    longest_side = max(width, height)
    shortest_side = max(min(width, height), 1)
    if fill_ratio < 0.5:
        return [mask]
    if longest_side / shortest_side >= 3.0 and fill_ratio < 0.45:
        return [mask]

    dense_parts = _split_dense_detail_cluster(mask)
    if len(dense_parts) > 1:
        return dense_parts

    binary = np.where(crop > 0, 255, 0).astype(np.uint8)
    distance = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    max_distance = float(distance.max())
    if max_distance < 6.0:
        return [mask]

    peak_kernel = np.ones((7, 7), np.uint8)
    local_max = cv2.dilate(distance, peak_kernel)
    sure_fg = np.where(
        np.logical_and(distance >= local_max - 1e-4, distance > max_distance * 0.7),
        255,
        0,
    ).astype(np.uint8)
    sure_fg = cv2.dilate(sure_fg, np.ones((3, 3), np.uint8), iterations=1)
    marker_count, markers = cv2.connectedComponents(sure_fg)
    if marker_count <= 2:
        sure_fg = np.where(distance >= max_distance * 0.45, 255, 0).astype(np.uint8)
        sure_fg = cv2.morphologyEx(sure_fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        marker_count, markers = cv2.connectedComponents(sure_fg)
    if marker_count <= 2:
        return [mask]

    sure_bg = cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=1)
    unknown = cv2.subtract(sure_bg, sure_fg)
    markers = markers + 1
    markers[unknown == 255] = 0
    watershed_input = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    segmented = cv2.watershed(watershed_input, markers)

    parts: list[np.ndarray] = []
    min_part_area = max(48, int(area * 0.12))
    for marker_id in range(2, int(segmented.max()) + 1):
        local_mask = np.where(segmented == marker_id, 255, 0).astype(np.uint8)
        if int(np.count_nonzero(local_mask)) < min_part_area:
            continue
        full_mask = np.zeros_like(mask)
        full_mask[y1:y2, x1:x2] = local_mask
        parts.append(full_mask)

    if len(parts) <= 1:
        return [mask]
    return parts


def _split_dense_detail_cluster(mask: np.ndarray) -> list[np.ndarray]:
    bbox = _mask_bbox(mask)
    if bbox is None:
        return [mask]
    x1, y1, x2, y2 = bbox
    crop = mask[y1:y2, x1:x2]
    if crop.size == 0:
        return [mask]

    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    micro_contours: list[tuple[tuple[float, float], np.ndarray]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 10.0 or area > 1400.0:
            continue
        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw > 42 or bh > 42:
            continue
        center = (bx + bw / 2.0, by + bh / 2.0)
        micro_contours.append((center, contour))
    if len(micro_contours) < 10:
        return [mask]

    equivalent_window_density = len(micro_contours) * 10000.0 / max((x2 - x1) * (y2 - y1), 1)
    if equivalent_window_density <= 10.0:
        return [mask]

    parts: list[np.ndarray] = []
    for _center, contour in micro_contours[:32]:
        local_mask = np.zeros_like(crop)
        cv2.drawContours(local_mask, [contour], -1, 255, -1)
        if int(np.count_nonzero(local_mask)) < 10:
            continue
        full_mask = np.zeros_like(mask)
        full_mask[y1:y2, x1:x2] = local_mask
        parts.append(full_mask)
    if len(parts) < 2:
        return [mask]
    return parts


def _is_complex_raster_candidate(image: np.ndarray, mask: np.ndarray) -> bool:
    bbox = _mask_bbox(mask)
    if bbox is None:
        return False
    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]
    local_mask = mask[y1:y2, x1:x2]
    if crop.size == 0 or local_mask.size == 0 or not np.any(local_mask > 0):
        return False

    width = max(x2 - x1, 1)
    height = max(y2 - y1, 1)
    area = width * height
    masked_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    masked_gray = cv2.bitwise_and(masked_gray, masked_gray, mask=local_mask)

    edges = cv2.Canny(masked_gray, 50, 150)
    edges = cv2.bitwise_and(edges, edges, mask=local_mask)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour_count = sum(1 for contour in contours if cv2.contourArea(contour) >= 6.0)

    pixels = crop[local_mask > 0].reshape(-1, 3)
    color_variance = float(np.var(masked_gray[local_mask > 0])) if np.any(local_mask > 0) else 0.0
    quantized = ((pixels.astype(np.int32) + 16) // 32) * 32
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    significant_colors = int(np.sum(counts >= max(len(pixels) * 0.08, 24)))

    fill_ratio = float(np.count_nonzero(local_mask)) / max(area, 1)
    if fill_ratio >= 0.88 and contour_count < 8 and color_variance < 500.0:
        return False

    return contour_count > 15 or significant_colors >= 3 or color_variance > 800.0


def _infer_shape_hint(mask: np.ndarray) -> str | None:
    bbox = _mask_bbox(mask)
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    crop = mask[y1:y2, x1:x2]
    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 24:
        return None
    shape = classify_contour(contour)
    if shape == SHAPE_TRIANGLE:
        return SHAPE_TRIANGLE
    if shape == SHAPE_POLYGON:
        perimeter = max(cv2.arcLength(contour, True), 1.0)
        approx = cv2.approxPolyDP(contour, max(2.0, perimeter * 0.03), True)
        if len(approx) == 5:
            return "pentagon"
    return None


def _compress_records(records: list[_ProposalRecord], image_width: int, image_height: int) -> list[_ProposalRecord]:
    image_area = max(image_width * image_height, 1)
    filtered = [
        record
        for record in records
        if _bbox_area(record.bbox) >= _min_component_area(record.proposal_type, image_area)
    ]

    merged: list[_ProposalRecord] = []
    for record in sorted(filtered, key=lambda item: _bbox_area(item.bbox), reverse=True):
        match_index = _find_record_merge_target(merged, record)
        if match_index is None:
            merged.append(record)
            continue
        merged[match_index] = _merge_two_records(merged[match_index], record)
    return sorted(merged, key=lambda item: (item.proposal_type, item.bbox[1], item.bbox[0]))



def _cluster_icon_candidate_records(
    records: list[_ProposalRecord],
    image_width: int,
    image_height: int,
) -> list[_ProposalRecord]:
    candidates = [
        (index, record)
        for index, record in enumerate(records)
        if record.proposal_type == 'region' and record.shape_hint == _RASTER_CANDIDATE_HINT
    ]
    if len(candidates) < 2:
        return records

    text_records = [record for record in records if record.proposal_type == 'text_like']
    adjacency: dict[int, set[int]] = {index: set() for index, _ in candidates}
    for pos, (left_index, left_record) in enumerate(candidates):
        for right_index, right_record in candidates[pos + 1:]:
            if _bbox_gap(left_record.bbox, right_record.bbox) > 15:
                continue
            adjacency[left_index].add(right_index)
            adjacency[right_index].add(left_index)

    visited: set[int] = set()
    consumed: set[int] = set()
    clustered: list[_ProposalRecord] = []
    image_area = max(image_width * image_height, 1)
    for start_index, _record in candidates:
        if start_index in visited:
            continue
        stack = [start_index]
        group: list[int] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            group.append(current)
            stack.extend(adjacency[current] - visited)
        if len(group) < 2:
            continue
        group_records = [records[idx] for idx in group]
        merged_record = _build_icon_cluster_record(group_records, text_records, image_width, image_height, image_area)
        if merged_record is None:
            continue
        consumed.update(group)
        clustered.append(merged_record)

    if not clustered:
        return records

    remaining = [record for index, record in enumerate(records) if index not in consumed]
    remaining.extend(clustered)
    return sorted(remaining, key=lambda item: (item.proposal_type, item.bbox[1], item.bbox[0]))


def _build_icon_cluster_record(
    records: list[_ProposalRecord],
    text_records: list[_ProposalRecord],
    image_width: int,
    image_height: int,
    image_area: int,
) -> _ProposalRecord | None:
    merged_bbox = [
        min(record.bbox[0] for record in records),
        min(record.bbox[1] for record in records),
        max(record.bbox[2] for record in records),
        max(record.bbox[3] for record in records),
    ]
    x1, y1, x2, y2 = merged_bbox
    local_mask = np.zeros((max(y2 - y1, 1), max(x2 - x1, 1)), dtype=np.uint8)
    for record in records:
        bx1, by1, bx2, by2 = record.bbox
        local_mask[by1 - y1:by2 - y1, bx1 - x1:bx2 - x1] = 255
    local_mask = cv2.dilate(local_mask, np.ones((5, 5), np.uint8), iterations=1)
    points = cv2.findNonZero(local_mask)
    if points is None:
        return None
    dx, dy, width, height = cv2.boundingRect(points)
    merged_bbox = [x1 + int(dx), y1 + int(dy), x1 + int(dx + width), y1 + int(dy + height)]
    if not _is_valid_icon_cluster_bbox(merged_bbox, records, image_area):
        return None
    if _icon_cluster_overlaps_text(merged_bbox, text_records):
        return None

    full_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    mx1, my1, mx2, my2 = merged_bbox
    full_mask[my1:my2, mx1:mx2] = 255
    return _ProposalRecord(
        bbox=merged_bbox,
        proposal_type='region',
        confidence=min(max(record.confidence for record in records) + 0.03, 0.99),
        mask=full_mask,
        shape_hint='icon_cluster',
    )


def _is_valid_icon_cluster_bbox(
    merged_bbox: list[int],
    members: list[_ProposalRecord],
    image_area: int,
) -> bool:
    width = max(merged_bbox[2] - merged_bbox[0], 1)
    height = max(merged_bbox[3] - merged_bbox[1], 1)
    area = width * height
    largest_member = max(_bbox_area(record.bbox) for record in members)
    total_member_area = sum(_bbox_area(record.bbox) for record in members)
    aspect_ratio = max(width / max(height, 1), height / max(width, 1))
    occupancy = total_member_area / max(area, 1)
    if area < int(largest_member * 1.15):
        return False
    if area > int(image_area * 0.12):
        return False
    if aspect_ratio > 4.5:
        return False
    if occupancy < 0.12:
        return False
    return True


def _icon_cluster_overlaps_text(merged_bbox: list[int], text_records: list[_ProposalRecord]) -> bool:
    cx = (merged_bbox[0] + merged_bbox[2]) / 2.0
    cy = (merged_bbox[1] + merged_bbox[3]) / 2.0
    for record in text_records:
        if _overlap_ratio(merged_bbox, record.bbox) >= 0.15:
            return True
        if record.bbox[0] <= cx <= record.bbox[2] and record.bbox[1] <= cy <= record.bbox[3]:
            return True
    return False


def _bbox_gap(left: list[int], right: list[int]) -> int:
    dx = max(left[0] - right[2], right[0] - left[2], 0)
    dy = max(left[1] - right[3], right[1] - left[3], 0)
    return max(dx, dy)


def _find_record_merge_target(existing: list[_ProposalRecord], incoming: _ProposalRecord) -> int | None:
    for index, current in enumerate(existing):
        if current.proposal_type != incoming.proposal_type:
            continue
        if _should_merge_records(current.bbox, incoming.bbox, current.shape_hint, incoming.shape_hint):
            return index
    return None


def _merge_two_records(left: _ProposalRecord, right: _ProposalRecord) -> _ProposalRecord:
    bbox = [
        min(left.bbox[0], right.bbox[0]),
        min(left.bbox[1], right.bbox[1]),
        max(left.bbox[2], right.bbox[2]),
        max(left.bbox[3], right.bbox[3]),
    ]
    merged_mask = left.mask if left.mask.size >= right.mask.size else right.mask
    return _ProposalRecord(
        bbox=bbox,
        proposal_type=left.proposal_type,
        confidence=max(left.confidence, right.confidence),
        mask=merged_mask,
        shape_hint=left.shape_hint or right.shape_hint,
    )


def _records_to_component_proposals(records: list[_ProposalRecord], masks_dir: Path) -> list[ComponentProposal]:
    proposals: list[ComponentProposal] = []
    for index, record in enumerate(records):
        component_id = f"{record.proposal_type}-{index:03d}"
        mask_name = f"{component_id}.png"
        write_image(masks_dir / mask_name, record.mask)
        proposals.append(
            ComponentProposal(
                component_id=component_id,
                bbox=record.bbox,
                mask_path=f"masks/{mask_name}",
                proposal_type=record.proposal_type,
                confidence=record.confidence,
                shape_hint=record.shape_hint,
            )
        )
    return proposals



def _limit_text_like_proposals(
    proposals: list[ComponentProposal],
    image_width: int,
    image_height: int,
) -> list[ComponentProposal]:
    text_like = [proposal for proposal in proposals if proposal.proposal_type == 'text_like']
    if not text_like:
        return proposals
    max_text_like = max(80, min(140, int((image_width * image_height) * 0.000007)))
    if len(text_like) <= max_text_like:
        return proposals

    ranked = sorted(
        text_like,
        key=lambda proposal: (-proposal.confidence, _bbox_area(proposal.bbox), proposal.bbox[1], proposal.bbox[0]),
    )
    keep_ids = {proposal.component_id for proposal in ranked[:max_text_like]}
    return [
        proposal
        for proposal in proposals
        if proposal.proposal_type != 'text_like' or proposal.component_id in keep_ids
    ]


def _ensure_mixed_component_types(
    proposals: list[ComponentProposal],
    width: int,
    height: int,
    masks_dir: Path,
) -> list[ComponentProposal]:
    if proposals:
        return proposals

    has_region = any(item.proposal_type == "region" for item in proposals)
    has_stroke = any(item.proposal_type == "stroke" for item in proposals)

    if not has_region:
        region_id = f"region-{len(proposals):03d}"
        region_mask = np.full((height, width), 255, dtype=np.uint8)
        mask_name = f"{region_id}.png"
        write_image(masks_dir / mask_name, region_mask)
        proposals.append(
            ComponentProposal(
                component_id=region_id,
                bbox=[0, 0, width, height],
                mask_path=f"masks/{mask_name}",
                proposal_type="region",
                confidence=0.51,
            )
        )

    if not has_stroke:
        stroke_id = f"stroke-{len(proposals):03d}"
        stroke_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.line(stroke_mask, (0, 0), (max(width - 1, 1), max(height - 1, 1)), 255, 1)
        mask_name = f"{stroke_id}.png"
        write_image(masks_dir / mask_name, stroke_mask)
        proposals.append(
            ComponentProposal(
                component_id=stroke_id,
                bbox=[0, 0, width, height],
                mask_path=f"masks/{mask_name}",
                proposal_type="stroke",
                confidence=0.34,
            )
        )

    return proposals


def _write_components_json(path: Path, proposals: list[ComponentProposal]) -> None:
    payload = [proposal.to_dict() for proposal in proposals]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _looks_like_dense_stroke_cluster(mask: np.ndarray) -> bool:
    bbox = _mask_bbox(mask)
    if bbox is None:
        return False
    x1, y1, x2, y2 = bbox
    crop = np.where(mask[y1:y2, x1:x2] > 0, 255, 0).astype(np.uint8)
    if crop.size == 0:
        return False
    width = x2 - x1
    height = y2 - y1
    bbox_area = max(width * height, 1)
    fill_ratio = float(np.count_nonzero(crop)) / bbox_area
    if fill_ratio >= 0.42 or min(width, height) < 24:
        return False
    distance = cv2.distanceTransform(crop, cv2.DIST_L2, 5)
    max_distance = float(distance.max())
    return max(width, height) >= 80 and max_distance <= 4.0


def _write_region_segmentation_debug(
    path: Path,
    proposals: list[ComponentProposal],
    masks_dir: Path,
    width: int,
    height: int,
) -> None:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    region_index = 0
    for proposal in proposals:
        if proposal.proposal_type != "region":
            continue
        region_index += 1
        mask_path = masks_dir / Path(proposal.mask_path).name
        mask = read_image(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
        x1, y1, x2, y2 = proposal.bbox
        target_w = max(x2 - x1, 1)
        target_h = max(y2 - y1, 1)
        if mask.shape[1] != target_w or mask.shape[0] != target_h:
            mask = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        color = np.array([
            (region_index * 73) % 255,
            (region_index * 151) % 255,
            (region_index * 197) % 255,
        ], dtype=np.uint8)
        region = canvas[y1:y2, x1:x2]
        region[mask > 0] = color
    write_image(path, canvas)


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image


def _scale_bbox_back(bbox: list[int], resize_scale: float) -> list[int]:
    if resize_scale >= 1.0:
        return bbox
    return [int(round(coord / resize_scale)) for coord in bbox]


# ---------------------------------------------------------------------------
# Hough circle injection
# ---------------------------------------------------------------------------

_HOUGH_OVERLAP_THRESHOLD = 0.70
_HOUGH_SIZE_RATIO = 3.0
_HOUGH_LARGE_BLOB_RATIO = 15.0
_HOUGH_MAX_INJECTED = 50


def _inject_hough_circles(
    image: np.ndarray,
    proposals: list[ComponentProposal],
    masks_dir: Path,
    width: int,
    height: int,
    cfg: PipelineConfig | None,
) -> list[ComponentProposal]:
    """Detect circles via Hough transform and inject as new proposals."""

    from .detect_shapes import detect_circles_hough

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    max_radius = max(min(width, height) // 4, 80)
    circles = detect_circles_hough(gray, min_radius=6, max_radius=max_radius)
    if not circles:
        return proposals

    image_area = max(width * height, 1)
    min_area = _min_component_area("region", image_area)
    injected: list[ComponentProposal] = []

    for cx, cy, r in circles:
        if len(injected) >= _HOUGH_MAX_INJECTED:
            break

        circle_area = int(3.14159 * r * r)
        if circle_area < min_area:
            continue

        circle_bbox = [
            max(cx - r, 0),
            max(cy - r, 0),
            min(cx + r, width),
            min(cy + r, height),
        ]

        # Dedup against already-injected circles
        dup_injected = False
        for prev in injected:
            if _overlap_ratio(prev.bbox, circle_bbox) >= _HOUGH_OVERLAP_THRESHOLD:
                dup_injected = True
                break
        if dup_injected:
            continue

        skip = False
        inside_large_blob = False
        for existing in proposals:
            existing_area = _bbox_area(existing.bbox)
            overlap = _overlap_ratio(existing.bbox, circle_bbox)
            area_ratio = max(existing_area, 1) / max(circle_area, 1)

            # Similar-size overlap → already detected
            if overlap >= _HOUGH_OVERLAP_THRESHOLD and (1.0 / _HOUGH_SIZE_RATIO) <= area_ratio <= _HOUGH_SIZE_RATIO:
                skip = True
                break

            # Circle inside large blob → candidate for injection
            if area_ratio >= _HOUGH_LARGE_BLOB_RATIO and overlap >= _HOUGH_OVERLAP_THRESHOLD:
                inside_large_blob = True

        if skip:
            continue
        if not inside_large_blob:
            continue
        if not _looks_like_round_region(image, circle_bbox, cx, cy, r):
            continue

        comp_id = f"region-hough-{len(proposals) + len(injected):03d}"
        # Use cropped mask to avoid OOM on large images
        bx1, by1, bx2, by2 = circle_bbox
        crop_h, crop_w = by2 - by1, bx2 - bx1
        mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
        cv2.circle(mask, (cx - bx1, cy - by1), r, 255, -1)
        mask_name = f"{comp_id}.png"
        write_image(masks_dir / mask_name, mask)

        injected.append(
            ComponentProposal(
                component_id=comp_id,
                bbox=circle_bbox,
                mask_path=f"masks/{mask_name}",
                proposal_type="region",
                confidence=0.75,
                shape_hint="circle",
            )
        )

    return proposals + injected


def _looks_like_round_region(
    image: np.ndarray,
    circle_bbox: list[int],
    center_x: int,
    center_y: int,
    radius: int,
) -> bool:
    bx1, by1, bx2, by2 = circle_bbox
    crop = image[by1:by2, bx1:bx2]
    if crop.size == 0:
        return False

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blurred = gaussian_blur(gray, (3, 3), 0)
    _, binary = threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    refined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(refined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False

    local_center = (float(center_x - bx1), float(center_y - by1))
    contour = _select_center_contour(contours, local_center, radius)
    if contour is None:
        return False

    area = cv2.contourArea(contour)
    if area < 16:
        return False
    circle_area = math.pi * radius * radius
    area_ratio = area / max(circle_area, 1.0)
    if area_ratio < 0.35 or area_ratio > 1.35:
        return False

    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 1e-6:
        return False
    circularity = 4.0 * math.pi * area / (perimeter * perimeter)
    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = w / max(h, 1)
    return 0.7 <= aspect_ratio <= 1.3 and circularity >= 0.55


def _select_center_contour(
    contours: list[np.ndarray],
    local_center: tuple[float, float],
    radius: int,
) -> np.ndarray | None:
    best: np.ndarray | None = None
    best_key: tuple[float, float, float] | None = None
    max_distance = max(radius * 0.45, 12.0)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 16:
            continue
        distance = abs(cv2.pointPolygonTest(contour, local_center, True))
        if distance > max_distance:
            continue
        contains_center = cv2.pointPolygonTest(contour, local_center, False) >= 0
        (cx, cy), _ = cv2.minEnclosingCircle(contour)
        center_distance = math.hypot(cx - local_center[0], cy - local_center[1])
        key = (0.0 if contains_center else 1.0, center_distance, -area)
        if best_key is None or key < best_key:
            best = contour
            best_key = key
    return best
