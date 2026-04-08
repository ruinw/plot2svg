from __future__ import annotations

from dataclasses import dataclass
import base64

import cv2
import numpy as np


@dataclass(frozen=True)
class IconComplexity:
    contour_count: int
    variance: float
    is_complex: bool


class IconProcessor:
    def __init__(self, contour_threshold: int = 15, variance_threshold: float = 800.0) -> None:
        self.contour_threshold = contour_threshold
        self.variance_threshold = variance_threshold

    def load_bgra(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        return image

    def evaluate_complexity(self, roi_bgra: np.ndarray) -> IconComplexity:
        bgr = cv2.cvtColor(roi_bgra, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour_count = len(contours)
        variance = float(np.var(gray))
        is_complex = contour_count > self.contour_threshold or variance > self.variance_threshold
        return IconComplexity(contour_count=contour_count, variance=variance, is_complex=is_complex)

    def encode_base64_png(self, roi_bgra: np.ndarray) -> str:
        success, buffer = cv2.imencode(".png", roi_bgra)
        if not success:
            raise RuntimeError("Failed to encode ROI as PNG")
        return base64.b64encode(buffer.tobytes()).decode("ascii")

    def build_image_tag(self, x: int, y: int, width: int, height: int, payload: str) -> str:
        return (
            f'<image x="{x}" y="{y}" width="{width}" height="{height}" '
            f'preserveAspectRatio="none" href="data:image/png;base64,{payload}" />'
        )

    def process_roi(self, roi_img: np.ndarray, x: int = 0, y: int = 0) -> tuple[IconComplexity, str | None]:
        roi_bgra = self.load_bgra(roi_img)
        complexity = self.evaluate_complexity(roi_bgra)
        if not complexity.is_complex:
            return complexity, None
        payload = self.encode_base64_png(roi_bgra)
        tag = self.build_image_tag(x, y, roi_bgra.shape[1], roi_bgra.shape[0], payload)
        return complexity, tag
