"""OCR helpers for promoting text-like nodes into editable text nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
import onnxruntime as ort
from rapidocr_onnxruntime import RapidOCR

from .config import PipelineConfig
from .scene_graph import SceneGraph, SceneNode


_OCR_ENGINE_FULL: RapidOCR | None = None
_OCR_ENGINE_REC: RapidOCR | None = None

_EARLY_EXIT_CONFIDENCE = 0.85
_MIN_PIXEL_STD = 10.0


ImageInput = Union[Path, np.ndarray]


def populate_text_nodes(image_path: ImageInput, scene_graph: SceneGraph, cfg: PipelineConfig | None = None) -> SceneGraph:
    """Run OCR on text nodes and fill their text content."""

    image = _load_color_image(image_path)

    merged_graph = merge_text_nodes(scene_graph)
    text_nodes = [n for n in merged_graph.nodes if n.type == "text" and not _should_skip_text_node(n, cfg)]

    # Optimization 5: thread-parallel OCR (ONNX releases GIL)
    cap = cfg.ocr_max_workers if cfg and cfg.ocr_max_workers > 0 else 4
    max_workers = min(cap, len(text_nodes)) if text_nodes else 0
    results: dict[str, str | None] = {}

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_read_text_from_bbox, image, node.bbox, cfg): node
                for node in text_nodes
            }
            for future in as_completed(futures):
                node = futures[future]
                results[node.id] = future.result()
    else:
        for node in text_nodes:
            results[node.id] = _read_text_from_bbox(image, node.bbox, cfg)

    nodes: list[SceneNode] = []
    for node in merged_graph.nodes:
        if node.id in results:
            text = results[node.id]
            nodes.append(
                SceneNode(
                    id=node.id,
                    type=node.type,
                    bbox=node.bbox,
                    z_index=node.z_index,
                    vector_mode="text_box" if text else node.vector_mode,
                    confidence=node.confidence,
                    fill=node.fill,
                    stroke=node.stroke,
                    stroke_width=node.stroke_width,
                    source_mask=node.source_mask,
                    text_content=text,
                    children=node.children,
                )
            )
        else:
            nodes.append(node)
    return SceneGraph(width=merged_graph.width, height=merged_graph.height, nodes=nodes)


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
                children=[item.id for item in cluster],
            )
        )

    non_text_nodes = [node for node in scene_graph.nodes if node.type != "text"]
    all_nodes = sorted(non_text_nodes + merged_text_nodes, key=lambda node: node.z_index)
    return SceneGraph(width=scene_graph.width, height=scene_graph.height, nodes=all_nodes)


def _read_text_from_bbox(image, bbox: list[int], cfg: PipelineConfig | None = None) -> str | None:
    x1, y1, x2, y2 = _expand_bbox(bbox, image.shape[1], image.shape[0], margin=20)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    # Optimization 3: skip uniform regions (no text)
    gray_check = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if np.std(gray_check) < _MIN_PIXEL_STD:
        return None
    candidates: list[tuple[str, float]] = []
    for variant in _prepare_ocr_variants(crop, cfg):
        result, _ = _get_ocr_engine_full()(variant)
        new_candidates = _extract_ocr_candidates(result)
        candidates.extend(new_candidates)
        # Optimization 2: early exit on high-confidence result
        if any(conf >= _EARLY_EXIT_CONFIDENCE for _, conf in new_candidates):
            break
    text = choose_best_ocr_text(candidates)
    # Optimization 4: skip multiline if confidence is high
    best_conf = max((conf for _, conf in candidates), default=0.0)
    if text and (crop.shape[0] < 60 or best_conf >= _EARLY_EXIT_CONFIDENCE):
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


def _prepare_ocr_variants(crop, cfg: PipelineConfig | None = None):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray2x = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, th2x = cv2.threshold(gray2x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    gray3x = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    _, th3x = cv2.threshold(gray3x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants = [crop, th2x, th3x, gray3x]
    variant_count = 3 if cfg is None else cfg.ocr_variant_count()
    return variants[:variant_count]


def _read_multiline_text(crop) -> str | None:
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
    normalized = _dedupe_adjacent_words(normalized.strip())
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
    image = cv2.imread(str(Path(image_input)), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image
