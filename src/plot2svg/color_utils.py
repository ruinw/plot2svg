"""Shared color and sampling helpers for the Plot2SVG pipeline."""

from __future__ import annotations

import cv2
import numpy as np


def _bgr_to_hex(color: tuple[int, int, int]) -> str:
    """Convert a BGR tuple to a CSS hex string.

    Args:
        color: Color in OpenCV BGR channel order.

    Returns:
        The corresponding ``#rrggbb`` string.
    """
    b, g, r = color
    return f"#{r:02x}{g:02x}{b:02x}"


def _hex_to_bgr(color: str | None) -> tuple[int, int, int] | None:
    """Convert a CSS hex string to a BGR tuple.

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


def _is_near_white(color: str | None) -> bool:
    """Return whether a hex color is visually close to white.

    Args:
        color: CSS hex color string.

    Returns:
        True when every channel is near the white end of the range.
    """
    if color is None or not color.startswith("#") or len(color) != 7:
        return False
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return False
    return min(r, g, b) >= 236


def _is_near_black(color: str | None) -> bool:
    """Return whether a color is visually close to black.

    Args:
        color: CSS color string.

    Returns:
        True when the color is pure black or all channels are very dark.
    """
    if color is None:
        return False
    lowered = color.lower()
    if lowered in {"#000000", "black"}:
        return True
    if not lowered.startswith("#") or len(lowered) != 7:
        return False
    try:
        r = int(lowered[1:3], 16)
        g = int(lowered[3:5], 16)
        b = int(lowered[5:7], 16)
    except ValueError:
        return False
    return max(r, g, b) <= 24


def _is_pure_black_region_fill(color: str | None) -> bool:
    """Return whether a fill should be treated as exactly black.

    Args:
        color: CSS color string.

    Returns:
        True when the fill is represented as black.
    """
    if color is None:
        return False
    return color.lower() in {"#000000", "black"}


def _is_dark_color(color: str) -> bool:
    """Return whether a CSS color should be treated as dark.

    Args:
        color: CSS color string.

    Returns:
        True when the color is dark enough for contrast-related checks.
    """
    if color in {"", "none"}:
        return False
    if color in {"#000000", "black"}:
        return True
    if not color.startswith("#") or len(color) != 7:
        return False
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except ValueError:
        return False
    return max(r, g, b) <= 32


def _is_light_hex(color: str | None) -> bool:
    """Return whether a CSS color should be treated as light.

    Args:
        color: CSS color string.

    Returns:
        True when the color is a light tone.
    """
    if color is None:
        return False
    lowered = color.lower()
    if lowered in {"", "none"}:
        return False
    if lowered in {"white", "#ffffff", "#fefefe", "#fcfcfc"}:
        return True
    if not lowered.startswith("#") or len(lowered) != 7:
        return False
    try:
        r = int(lowered[1:3], 16)
        g = int(lowered[3:5], 16)
        b = int(lowered[5:7], 16)
    except ValueError:
        return False
    return min(r, g, b) >= 140 or (r + g + b) >= 560


def _is_light_container_color(fill: str, stroke: str) -> bool:
    """Return whether a container should be treated as visually light.

    Args:
        fill: Fill color string.
        stroke: Stroke color string.

    Returns:
        True when either color is light and neither is near black.
    """
    if _is_near_black(fill) or _is_near_black(stroke):
        return False
    return _is_light_hex(fill) or _is_light_hex(stroke)


def _sample_panel_fill(image: np.ndarray, bbox: list[int]) -> str | None:
    """Sample the dominant non-white fill color inside a panel bbox.

    Args:
        image: Source BGR image.
        bbox: Panel bounding box in xyxy format.

    Returns:
        The dominant sampled fill color as ``#rrggbb``, or None.
    """
    x1, y1, x2, y2 = _clamp_bbox_to_image(bbox, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = (gray < 245) | (hsv[:, :, 1] > 12)
    if not np.any(mask):
        return None
    pixels = crop[mask].reshape(-1, 3)
    quantized = ((pixels.astype(np.int32) + 8) // 16) * 16
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    b, g, r = [int(np.clip(channel, 0, 255)) for channel in dominant]
    return f"#{r:02x}{g:02x}{b:02x}"


def _sample_panel_border_color(source_image: np.ndarray, bbox: list[int]) -> tuple[int, int, int] | None:
    """Sample the dominant saturated border color around a panel bbox.

    Args:
        source_image: Source BGR image.
        bbox: Panel bounding box in xyxy format.

    Returns:
        The dominant BGR border color, or None.
    """
    x1, y1, x2, y2 = _clamp_bbox_to_image(bbox, source_image.shape[1], source_image.shape[0])
    border_mask = np.zeros(source_image.shape[:2], dtype=np.uint8)
    cv2.rectangle(border_mask, (x1, y1), (x2 - 1, y2 - 1), 255, 8)
    pixels = source_image[border_mask > 0]
    if pixels.size == 0:
        return None
    hsv_pixels = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    saturated = pixels[(hsv_pixels[:, 1] > 35) & (pixels.max(axis=1) < 240)]
    if saturated.size == 0:
        return None
    quantized = np.clip(((saturated.astype(np.int32) + 8) // 16) * 16, 0, 255)
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    return int(dominant[0]), int(dominant[1]), int(dominant[2])


def _sample_arrow_fill_color(image: np.ndarray, bbox: list[int], fallback_color: tuple[int, int, int]) -> str:
    """Sample the dominant colored fill inside an arrow bbox.

    Args:
        image: Source BGR image.
        bbox: Arrow bounding box in xyxy format.
        fallback_color: BGR color used when sampling fails.

    Returns:
        The sampled arrow fill as ``#rrggbb``.
    """
    x1, y1, x2, y2 = _clamp_bbox_to_image(bbox, image.shape[1], image.shape[0])
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return _bgr_to_hex(fallback_color)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = (hsv[:, :, 1] > 35) & (gray < 220)
    if not np.any(mask):
        return _bgr_to_hex(fallback_color)
    pixels = crop[mask].reshape(-1, 3)
    quantized = ((pixels.astype(np.int32) + 8) // 16) * 16
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colors[int(np.argmax(counts))]
    return _bgr_to_hex((int(dominant[0]), int(dominant[1]), int(dominant[2])))


def _clamp_bbox_to_image(bbox: list[int], width: int, height: int) -> tuple[int, int, int, int]:
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
