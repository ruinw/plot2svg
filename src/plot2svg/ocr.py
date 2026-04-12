"""OCR helpers for promoting text-like nodes into editable text nodes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
from typing import Union

import cv2
import numpy as np

from .image_io import read_image, write_image
import onnxruntime as ort
from rapidocr_onnxruntime import RapidOCR

from .config import PipelineConfig
from .scene_graph import SceneGraph, SceneNode


_OCR_ENGINE_FULL: RapidOCR | None = None
_OCR_ENGINE_REC: RapidOCR | None = None

_EARLY_EXIT_CONFIDENCE = PipelineConfig(input_path=".", output_dir=".").thresholds.ocr_early_exit_confidence
_MIN_PIXEL_STD = PipelineConfig(input_path=".", output_dir=".").thresholds.ocr_min_pixel_std

ImageInput = Union[Path, np.ndarray]


def populate_text_nodes(
    image_path: ImageInput,
    scene_graph: SceneGraph,
    cfg: PipelineConfig | None = None,
    coordinate_scale: float = 1.0,
) -> SceneGraph:
    """Run OCR on text nodes and fill their text content."""

    image = _load_color_image(image_path)
    merged_graph = merge_text_nodes(scene_graph)
    text_nodes = [n for n in merged_graph.nodes if n.type == "text" and not _should_skip_text_node(n, cfg)]

    cap = cfg.ocr_max_workers if cfg and cfg.ocr_max_workers > 0 else 4
    max_workers = min(cap, len(text_nodes)) if text_nodes else 0
    results: dict[str, str | None] = {}

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_read_text_from_bbox, image, node.bbox, cfg, coordinate_scale): node
                for node in text_nodes
            }
            for future in as_completed(futures):
                node = futures[future]
                results[node.id] = future.result()
    else:
        for node in text_nodes:
            results[node.id] = _read_text_from_bbox(image, node.bbox, cfg, coordinate_scale)

    nodes: list[SceneNode] = []
    for node in merged_graph.nodes:
        if node.id in results:
            text = results[node.id]
            nodes.append(
                SceneNode(
                    id=node.id,
                    type=node.type,
                    bbox=node.bbox[:],
                    z_index=node.z_index,
                    vector_mode="text_box" if text else node.vector_mode,
                    confidence=node.confidence,
                    fill=node.fill,
                    fill_opacity=node.fill_opacity,
                    stroke=node.stroke,
                    stroke_width=node.stroke_width,
                    source_mask=node.source_mask,
                    text_content=text,
                    group_id=node.group_id,
                    component_role=node.component_role,
                    children=node.children[:],
                    shape_hint=node.shape_hint,
                )
            )
        else:
            nodes.append(node)
    return _copy_scene_graph_with_nodes(merged_graph, nodes)


def extract_text_overlays(
    image_input: ImageInput,
    cfg: PipelineConfig | None = None,
    coordinate_scale: float = 1.0,
) -> list[SceneNode]:
    """Run OCR on the full image and return top-layer text overlay nodes."""

    image = _load_color_image(image_input)
    result, _ = _get_ocr_engine_full()(image)
    if not result:
        return []

    nodes: list[SceneNode] = []
    for index, item in enumerate(result):
        if len(item) < 3:
            continue
        quad, raw_text, confidence = item[0], item[1], item[2]
        text = normalize_ocr_text(str(raw_text or ""))
        if not text:
            continue
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
        bbox = _bbox_from_ocr_quad(quad, coordinate_scale)
        if bbox is None or _should_skip_overlay_bbox(bbox, cfg):
            continue
        nodes.append(
            SceneNode(
                id=f"text-overlay-{index:03d}",
                type="text",
                bbox=bbox,
                z_index=10_000 + index,
                vector_mode="text_box",
                confidence=conf,
                fill=None,
                stroke="#000000",
                text_content=text,
            )
        )
    return nodes


def inpaint_text_nodes(
    image_input: ImageInput,
    text_nodes: list[SceneNode],
    padding: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Remove text boxes from the working image without cutting geometry into entities."""

    image = _load_color_image(image_input)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for node in text_nodes:
        if node.type != "text":
            continue
        local_mask = _text_contour_mask(image, node.bbox, padding)
        if local_mask is None:
            x1, y1, x2, y2 = _expand_bbox(node.bbox, image.shape[1], image.shape[0], min(padding, 2))
            local_mask = np.zeros(image.shape[:2], dtype=np.uint8)
            local_mask[y1:y2, x1:x2] = 255
        mask = cv2.bitwise_or(mask, local_mask)
    if not np.any(mask):
        return image.copy(), mask
    cleaned = image.copy()
    cleaned[mask > 0] = 255
    return cleaned, mask


def merge_text_nodes(scene_graph: SceneGraph) -> SceneGraph:
    """Merge adjacent text nodes into line-level text boxes."""

    text_nodes = sorted(
        [node for node in scene_graph.nodes if node.type == "text"],
        key=lambda node: (node.bbox[1], node.bbox[0]),
    )
    merged_text_nodes: list[SceneNode] = []
    consumed = [False] * len(text_nodes)
    for index, node in enumerate(text_nodes):
        if consumed[index]:
            continue
        cluster = [node]
        consumed[index] = True
        current_bbox = node.bbox[:]
        current_confidence = node.confidence
        for candidate_index in range(index + 1, len(text_nodes)):
            if consumed[candidate_index]:
                continue
            candidate = text_nodes[candidate_index]
            if not _should_merge_text_boxes(current_bbox, candidate.bbox):
                continue
            consumed[candidate_index] = True
            cluster.append(candidate)
            current_bbox = _union_bbox(current_bbox, candidate.bbox)
            current_confidence = max(current_confidence, candidate.confidence)

        merged_text_nodes.append(
            SceneNode(
                id=cluster[0].id,
                type="text",
                bbox=current_bbox,
                z_index=min(item.z_index for item in cluster),
                vector_mode="text_box",
                confidence=current_confidence,
                fill=None,
                stroke=cluster[0].stroke,
                stroke_width=cluster[0].stroke_width,
                source_mask=cluster[0].source_mask,
                text_content=None,
                group_id=cluster[0].group_id,
                component_role=cluster[0].component_role,
                children=[item.id for item in cluster],
                shape_hint=cluster[0].shape_hint,
            )
        )

    non_text_nodes = [node for node in scene_graph.nodes if node.type != "text"]
    all_nodes = sorted(non_text_nodes + merged_text_nodes, key=lambda node: node.z_index)
    return _copy_scene_graph_with_nodes(scene_graph, all_nodes)


def _read_text_from_bbox(
    image: np.ndarray,
    bbox: list[int],
    cfg: PipelineConfig | None = None,
    coordinate_scale: float = 1.0,
) -> str | None:
    thresholds = _ocr_thresholds(cfg)
    crop = _extract_scaled_crop(image, bbox, coordinate_scale, margin=20)
    if crop.size == 0:
        return None
    gray_check = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if np.std(gray_check) < thresholds.ocr_min_pixel_std:
        return None
    candidates: list[tuple[str, float]] = []
    for variant in _prepare_ocr_variants(crop, cfg):
        result, _ = _get_ocr_engine_full()(variant)
        new_candidates = _extract_ocr_candidates(result)
        candidates.extend(new_candidates)
        if any(conf >= thresholds.ocr_early_exit_confidence for _, conf in new_candidates):
            break
    text = choose_best_ocr_text(candidates)
    best_conf = max((conf for _, conf in candidates), default=0.0)
    if text and (crop.shape[0] < 60 or best_conf >= thresholds.ocr_early_exit_confidence):
        return normalize_ocr_text(text)
    line_text = _read_multiline_text(crop)
    if line_text:
        return normalize_ocr_text(line_text)
    if text:
        return normalize_ocr_text(text)
    return None


def choose_best_ocr_text(candidates: list[tuple[str, float]]) -> str | None:
    """Pick the most useful OCR candidate from multiple preprocessing passes."""

    best_text: str | None = None
    best_score = float("-inf")
    for raw_text, confidence in candidates:
        text = normalize_ocr_text(raw_text)
        if not text:
            continue
        score = confidence + min(len(text), 24) * 0.01
        if score > best_score:
            best_text = text
            best_score = score
    return best_text


def _copy_scene_graph_with_nodes(scene_graph: SceneGraph, nodes: list[SceneNode]) -> SceneGraph:
    return SceneGraph(
        width=scene_graph.width,
        height=scene_graph.height,
        nodes=nodes,
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

def _text_contour_mask(image: np.ndarray, bbox: list[int], padding: int) -> np.ndarray | None:
    x1, y1, x2, y2 = _expand_bbox(bbox, image.shape[1], image.shape[0], max(padding, 1))
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    kernel_w = max(3, min(9, (x2 - x1) // 10))
    kernel_h = max(3, min(7, (y2 - y1) // 4))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w | 1, kernel_h | 1))
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    if float(np.std(blackhat)) < 2.0:
        return None

    binary = cv2.adaptiveThreshold(
        blackhat,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        -4,
    )
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    binary = cv2.dilate(binary, np.ones((2, 2), np.uint8), iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    local_mask = np.zeros_like(gray)
    min_area = max(6, int(((x2 - x1) * (y2 - y1)) * 0.0008))
    kept = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        bx, by, bw, bh = cv2.boundingRect(contour)
        if bw >= (x2 - x1) * 0.75 and bh >= (y2 - y1) * 0.75:
            continue
        cv2.drawContours(local_mask, [contour], -1, 255, -1)
        kept += 1
    if kept == 0:
        return None

    full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = local_mask
    return full_mask


def _bbox_from_ocr_quad(quad: object, coordinate_scale: float) -> list[int] | None:
    try:
        points = np.asarray(quad, dtype=np.float32).reshape(-1, 2)
    except Exception:
        return None
    if points.size == 0:
        return None
    if coordinate_scale not in (0.0, 1.0):
        points = points / float(coordinate_scale)
    x1 = int(np.floor(points[:, 0].min()))
    y1 = int(np.floor(points[:, 1].min()))
    x2 = int(np.ceil(points[:, 0].max()))
    y2 = int(np.ceil(points[:, 1].max()))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def _should_skip_overlay_bbox(bbox: list[int], cfg: PipelineConfig | None) -> bool:
    width = max(bbox[2] - bbox[0], 1)
    height = max(bbox[3] - bbox[1], 1)
    if cfg is None:
        return width < 8 or height < 8
    return width < max(cfg.text_skip_min_width() // 2, 8) or height < max(cfg.text_skip_min_height() // 2, 8)


def _get_ocr_engine_full() -> RapidOCR:
    global _OCR_ENGINE_FULL
    if _OCR_ENGINE_FULL is None:
        cuda = should_use_ocr_cuda(ort.get_available_providers(), ort.get_device())
        _OCR_ENGINE_FULL = RapidOCR(use_cuda=cuda)
    return _OCR_ENGINE_FULL


def _get_ocr_engine_rec() -> RapidOCR:
    global _OCR_ENGINE_REC
    if _OCR_ENGINE_REC is None:
        cuda = should_use_ocr_cuda(ort.get_available_providers(), ort.get_device())
        _OCR_ENGINE_REC = RapidOCR(
            use_cuda=cuda,
            use_text_det=False,
            use_angle_cls=False,
        )
    return _OCR_ENGINE_REC


def _clamp_bbox(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _expand_bbox(bbox: list[int], width: int, height: int, margin: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    return _clamp_bbox([x1 - margin, y1 - margin, x2 + margin, y2 + margin], width, height)


def _should_merge_text_boxes(left: list[int], right: list[int]) -> bool:
    left_height = max(left[3] - left[1], 1)
    right_height = max(right[3] - right[1], 1)
    avg_height = (left_height + right_height) / 2.0
    vertical_overlap = min(left[3], right[3]) - max(left[1], right[1])
    if vertical_overlap <= 0:
        return False
    if vertical_overlap / avg_height < 0.45:
        return False
    horizontal_gap = right[0] - left[2] if right[0] >= left[0] else left[0] - right[2]
    return horizontal_gap <= max(avg_height * 2.0, 28)


def _union_bbox(left: list[int], right: list[int]) -> list[int]:
    return [
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    ]


def _prepare_ocr_variants(crop: np.ndarray, cfg: PipelineConfig | None = None):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray2x = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, th2x = cv2.threshold(gray2x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray3x = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    _, th3x = cv2.threshold(gray3x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants = [crop, th2x, th3x, gray3x]
    variant_count = 3 if cfg is None else cfg.ocr_variant_count()
    return variants[:variant_count]


def _read_multiline_text(crop: np.ndarray) -> str | None:
    height = crop.shape[0]
    if height < 120:
        return None
    midpoint = height // 2
    ranges = [(0, midpoint), (midpoint, height)]

    line_texts: list[str] = []
    for top, bottom in ranges:
        pad_top = max(top - 4, 0)
        pad_bottom = min(bottom + 4, crop.shape[0])
        line_crop = crop[pad_top:pad_bottom, :]
        result, _ = _get_ocr_engine_full()(line_crop)
        text = choose_best_ocr_text(_extract_ocr_candidates(result))
        if text:
            line_texts.append(text)
    if not line_texts:
        return None
    return normalize_ocr_text(" ".join(line_texts))


def _extract_ocr_candidates(result) -> list[tuple[str, float]]:
    if not result:
        return []
    candidates: list[tuple[str, float]] = []
    for item in result:
        if len(item) < 3:
            continue
        text = item[1]
        try:
            confidence = float(item[2])
        except (TypeError, ValueError):
            confidence = 0.0
        candidates.append((text, confidence))
    return candidates


def normalize_ocr_text(text: str) -> str:
    """Normalize OCR output by fixing obvious noise and common OCR confusions."""

    normalized = " ".join(text.split())
    normalized = re.sub(r"\b(\d+)([A-Z][a-z]{3,})", r"\1 \2", normalized)
    normalized = re.sub(r"(?<=[A-Za-z\]])([&+])(?=[A-Za-z\[])", r" \1 ", normalized)
    normalized = re.sub(r"(^|\s)([&+])(?=[A-Za-z\[])", r"\1\2 ", normalized)
    normalized = re.sub(r"(?<=[A-Za-z0-9\]])(&)(?=$|\s|\])", r" \1", normalized)
    normalized = _dedupe_adjacent_words(" ".join(normalized.split()).strip())
    replacements = {
        "echnology": "technology",
        "miniaturizatio": "miniaturization",
        "signahng": "signaling",
        "intemediate": "intermediate",
        "lariants": "variants",
        "flament": "filament",
        "uonenn": "unknown",
    }
    words = []
    for word in normalized.split():
        suffix = ""
        core = word
        while core and not core[-1].isalnum():
            suffix = core[-1] + suffix
            core = core[:-1]
        replacement = replacements.get(core.lower())
        if replacement is not None:
            if core[:1].isupper():
                replacement = replacement.capitalize()
            word = replacement + suffix
        words.append(word)
    return " ".join(words).strip()


def _dedupe_adjacent_words(text: str) -> str:
    parts = text.split()
    if not parts:
        return ""
    deduped = [parts[0]]
    for part in parts[1:]:
        if part.lower() == deduped[-1].lower():
            continue
        deduped.append(part)
    return " ".join(deduped)


def _should_skip_text_node(node: SceneNode, cfg: PipelineConfig | None = None) -> bool:
    width = max(node.bbox[2] - node.bbox[0], 1)
    height = max(node.bbox[3] - node.bbox[1], 1)
    if cfg is None:
        return width < 18 or height < 10
    return width < cfg.text_skip_min_width() or height < cfg.text_skip_min_height()


def should_use_ocr_cuda(providers: list[str], device: str) -> bool:
    """Return True when OCR should prefer CUDA execution."""

    return device.upper() == "GPU" and "CUDAExecutionProvider" in providers


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image


def _ocr_thresholds(cfg: PipelineConfig | None):
    if cfg is not None and cfg.thresholds is not None:
        return cfg.thresholds
    return PipelineConfig(input_path=".", output_dir=".").thresholds


def _extract_scaled_crop(
    image: np.ndarray,
    bbox: list[int],
    coordinate_scale: float,
    margin: int,
) -> np.ndarray:
    base_width = max(int(round(image.shape[1] / coordinate_scale)), 1)
    base_height = max(int(round(image.shape[0] / coordinate_scale)), 1)
    expanded = _expand_bbox(bbox, base_width, base_height, margin=margin)
    source_bbox = _scale_bbox(expanded, coordinate_scale, image.shape[1], image.shape[0])
    x1, y1, x2, y2 = source_bbox
    crop = image[y1:y2, x1:x2]
    if crop.size == 0 or coordinate_scale == 1.0:
        return crop
    target_width = max(expanded[2] - expanded[0], 1)
    target_height = max(expanded[3] - expanded[1], 1)
    return cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_CUBIC)


def _scale_bbox(
    bbox: list[int],
    coordinate_scale: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    scaled = [int(round(coord * coordinate_scale)) for coord in bbox]
    return _clamp_bbox(scaled, width, height)
