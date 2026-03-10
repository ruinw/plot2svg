"""Component proposal generation for Plot2SVG."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import cv2
import numpy as np

from .config import PipelineConfig
from .gpu import gaussian_blur, resize, threshold

@dataclass(slots=True)
class _ProposalRecord:
    bbox: list[int]
    proposal_type: str
    confidence: float
    mask: np.ndarray


@dataclass(slots=True)
class ComponentProposal:
    """A raw component proposal extracted from an image."""

    component_id: str
    bbox: list[int]
    mask_path: str
    proposal_type: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def propose_components(image_path: Path, output_dir: Path, cfg: PipelineConfig | None = None) -> list[ComponentProposal]:
    """Generate mask proposals from an image using contour extraction."""

    output_dir.mkdir(parents=True, exist_ok=True)
    masks_dir = output_dir / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)

    image = cv2.imread(str(Path(image_path)), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")

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
    if resize_scale < 1.0:
        records.extend(_extract_records(image, resize_scale=1.0, text_only=True, min_area=10))

    records = _compress_records(records, original_width, original_height)
    proposals = _records_to_component_proposals(records, masks_dir)
    proposals = compress_proposals(proposals, original_width, original_height)
    proposals = _ensure_mixed_component_types(proposals, original_width, original_height, masks_dir)
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
    else:
        _, binary = threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8) if text_only else np.ones((3, 3), np.uint8)
    refined = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    refined = cv2.morphologyEx(refined, cv2.MORPH_CLOSE, kernel)

    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(refined, connectivity=8)
    records: list[_ProposalRecord] = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area < min_area:
            continue
        proposal_type = classify_component_role(width, height, area)
        if text_only and proposal_type != "text_like":
            continue
        component_mask = np.where(labels == label, 255, 0).astype(np.uint8)
        confidence = min(0.5 + (area / max(width * height, 1)), 0.99)
        records.append(
            _ProposalRecord(
                bbox=_scale_bbox_back([int(x), int(y), int(x + width), int(y + height)], resize_scale),
                proposal_type=proposal_type,
                confidence=float(confidence),
                mask=component_mask,
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
        if _overlap_ratio(current.bbox, incoming.bbox) >= 0.82:
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


def _find_record_merge_target(existing: list[_ProposalRecord], incoming: _ProposalRecord) -> int | None:
    for index, current in enumerate(existing):
        if current.proposal_type != incoming.proposal_type:
            continue
        if _overlap_ratio(current.bbox, incoming.bbox) >= 0.82:
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
    )


def _records_to_component_proposals(records: list[_ProposalRecord], masks_dir: Path) -> list[ComponentProposal]:
    proposals: list[ComponentProposal] = []
    for index, record in enumerate(records):
        component_id = f"{record.proposal_type}-{index:03d}"
        mask_name = f"{component_id}.png"
        cv2.imwrite(str(masks_dir / mask_name), record.mask)
        proposals.append(
            ComponentProposal(
                component_id=component_id,
                bbox=record.bbox,
                mask_path=f"masks/{mask_name}",
                proposal_type=record.proposal_type,
                confidence=record.confidence,
            )
        )
    return proposals


def _ensure_mixed_component_types(
    proposals: list[ComponentProposal],
    width: int,
    height: int,
    masks_dir: Path,
) -> list[ComponentProposal]:
    has_region = any(item.proposal_type == "region" for item in proposals)
    has_stroke = any(item.proposal_type == "stroke" for item in proposals)

    if not has_region:
        region_id = f"region-{len(proposals):03d}"
        region_mask = np.full((height, width), 255, dtype=np.uint8)
        mask_name = f"{region_id}.png"
        cv2.imwrite(str(masks_dir / mask_name), region_mask)
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
        cv2.imwrite(str(masks_dir / mask_name), stroke_mask)
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


def _scale_bbox_back(bbox: list[int], resize_scale: float) -> list[int]:
    if resize_scale >= 1.0:
        return bbox
    return [int(round(coord / resize_scale)) for coord in bbox]
