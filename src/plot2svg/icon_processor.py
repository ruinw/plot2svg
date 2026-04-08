"""Complex icon fallback helpers."""

from __future__ import annotations

from dataclasses import dataclass
import base64

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class IconComplexity:
    """Complexity metrics used to decide raster fallback."""

    contour_count: int
    significant_colors: int
    variance: float
    black_fill_risk: bool
    is_complex: bool


class IconProcessor:
    """Evaluate complex icon regions and encode them as embedded PNGs."""

    def __init__(self, contour_threshold: int = 15, variance_threshold: float = 800.0) -> None:
        self.contour_threshold = contour_threshold
        self.variance_threshold = variance_threshold

    def evaluate_complexity(self, crop: np.ndarray) -> IconComplexity:
        if crop.ndim == 2:
            bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        elif crop.shape[2] == 4:
            bgr = cv2.cvtColor(crop, cv2.COLOR_BGRA2BGR)
        else:
            bgr = crop
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour_count = sum(1 for contour in contours if cv2.contourArea(contour) >= 6.0)
        variance = float(np.var(gray))
        significant_colors = self._count_significant_nonwhite_colors(bgr)
        black_fill_risk = self._has_black_fill_risk(bgr, contours)
        is_complex = (
            contour_count > self.contour_threshold
            or significant_colors >= 3
            or variance > self.variance_threshold
            or black_fill_risk
        )
        return IconComplexity(
            contour_count=contour_count,
            significant_colors=significant_colors,
            variance=variance,
            black_fill_risk=black_fill_risk,
            is_complex=is_complex,
        )

    def encode_image_href(self, crop: np.ndarray) -> str:
        success, encoded = cv2.imencode('.png', crop)
        if not success:
            raise RuntimeError('Failed to encode ROI as PNG')
        payload = base64.b64encode(encoded.tobytes()).decode('ascii')
        return f'data:image/png;base64,{payload}'

    def _count_significant_nonwhite_colors(self, bgr: np.ndarray) -> int:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = (gray < 245) | (hsv[:, :, 1] > 18)
        pixels = bgr[mask]
        if len(pixels) == 0:
            return 0
        quantized = ((pixels.astype(np.int32) + 12) // 24) * 24
        _colors, counts = np.unique(quantized, axis=0, return_counts=True)
        threshold = max(int(len(pixels) * 0.03), 12)
        return int(np.sum(counts >= threshold))

    def _has_black_fill_risk(self, bgr: np.ndarray, contours: list[np.ndarray]) -> bool:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        dark_mask = gray < 72
        dark_ratio = float(np.count_nonzero(dark_mask)) / max(float(gray.size), 1.0)
        if dark_ratio < 0.05 or not contours:
            return False
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 24.0:
            return False
        perimeter = max(cv2.arcLength(largest, True), 1.0)
        approx = cv2.approxPolyDP(largest, max(1.5, perimeter * 0.03), True)
        complex_turns = len(approx) >= 8
        long_contours = sum(1 for contour in contours if cv2.arcLength(contour, True) >= 24.0)
        return complex_turns or long_contours >= 4
