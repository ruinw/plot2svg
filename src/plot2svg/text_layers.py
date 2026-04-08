"""Text and graphics layer separation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import cv2
import numpy as np

from .image_io import read_image, write_image


ImageInput = Union[Path, np.ndarray]


@dataclass(slots=True)
class TextGraphicLayers:
    """Separated raster layers used by the pipeline."""

    text_mask: np.ndarray
    text_layer: np.ndarray
    graphic_layer: np.ndarray


def separate_text_graphics(image_input: ImageInput) -> TextGraphicLayers:
    """Split an image into text-focused and graphics-focused layers."""

    image = _load_color_image(image_input)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresholded = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        11,
    )
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, _text_dilate_kernel(image.shape[1], image.shape[0]))
    connected = cv2.dilate(thresholded, dilate_kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    text_mask = np.zeros_like(gray)
    image_area = max(image.shape[0] * image.shape[1], 1)
    fallback_used = False
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if not _looks_like_text_bbox(width, height, image.shape[1], image.shape[0], image_area):
            continue
        cv2.drawContours(text_mask, [contour], -1, 255, -1)

    if not np.any(text_mask):
        text_mask = _fallback_text_mask(gray)
        fallback_used = bool(np.any(text_mask))

    dilation_kernel = np.ones((2, 2), dtype=np.uint8)
    refined_mask = cv2.dilate(text_mask, dilation_kernel, iterations=1)
    text_layer = cv2.bitwise_and(image, image, mask=refined_mask)
    graphic_mask = cv2.erode(text_mask, np.ones((3, 3), dtype=np.uint8), iterations=1) if np.any(text_mask) else refined_mask
    if np.any(text_mask) and not np.any(graphic_mask):
        graphic_mask = text_mask
    if np.any(graphic_mask):
        graphic_layer = _close_masked_graphics(image, graphic_mask, kernel_size=3 if fallback_used else 5)
    else:
        graphic_layer = image.copy()
    return TextGraphicLayers(
        text_mask=refined_mask,
        text_layer=text_layer,
        graphic_layer=graphic_layer,
    )


def _close_masked_graphics(image: np.ndarray, mask: np.ndarray, kernel_size: int) -> np.ndarray:
    graphic_layer = image.copy()
    if not np.any(mask):
        return graphic_layer

    kernel_size = max(kernel_size | 1, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))

    num_labels, labels, _stats, _ = cv2.connectedComponentsWithStats(
        np.where(mask > 0, 255, 0).astype(np.uint8),
        connectivity=8,
    )
    for label in range(1, num_labels):
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
        color_delta = np.max(np.abs(image.astype(np.int16) - dominant.astype(np.int16)), axis=2)
        replace_mask = (component_mask > 0) & (color_delta >= 80)
        graphic_layer[replace_mask] = dominant

    return graphic_layer


def write_text_graphic_layers(output_dir: Path, prefix: str, layers: TextGraphicLayers) -> None:
    """Persist debug artifacts for separated text/graphics layers."""

    output_dir.mkdir(parents=True, exist_ok=True)
    write_image(output_dir / f"{prefix}_text_mask.png", layers.text_mask)
    write_image(output_dir / f"{prefix}_text_layer.png", layers.text_layer)
    write_image(output_dir / f"{prefix}_graphic_layer.png", layers.graphic_layer)


def _looks_like_text_bbox(
    width: int,
    height: int,
    image_width: int,
    image_height: int,
    image_area: int,
) -> bool:
    if width < 6 or height < 6:
        return False
    if height > max(96, int(image_height * 0.12)):
        return False
    if width > int(image_width * 0.7):
        return False
    if width * height > image_area * 0.08:
        return False
    aspect_ratio = width / max(height, 1)
    return 0.6 <= aspect_ratio <= 20.0


def _text_dilate_kernel(image_width: int, image_height: int) -> tuple[int, int]:
    width = max(3, min(7, image_width // 250))
    height = max(3, min(5, image_height // 300))
    return (width, height)


def _fallback_text_mask(gray: np.ndarray) -> np.ndarray:
    blackhat = cv2.morphologyEx(
        gray,
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
    )
    _, binary = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    fallback_mask = np.zeros_like(gray)
    image_height, image_width = gray.shape[:2]
    image_area = max(image_width * image_height, 1)
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if not _looks_like_blackhat_glyph(width, height, area, image_width, image_height, image_area):
            continue
        fallback_mask[labels == label] = 255
    return fallback_mask


def _looks_like_blackhat_glyph(
    width: int,
    height: int,
    area: int,
    image_width: int,
    image_height: int,
    image_area: int,
) -> bool:
    if width < 3 or height < 6:
        return False
    if width > max(36, int(image_width * 0.14)):
        return False
    if height > max(40, int(image_height * 0.2)):
        return False
    if area > image_area * 0.02:
        return False
    fill_ratio = area / max(width * height, 1)
    aspect_ratio = width / max(height, 1)
    return fill_ratio >= 0.2 and 0.12 <= aspect_ratio <= 3.5


def _load_color_image(image_input: ImageInput) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        if image_input.ndim == 2:
            return cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
        return image_input
    image = read_image(Path(image_input), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to read image: {image_input}")
    return image