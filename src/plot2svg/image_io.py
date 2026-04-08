"""Unicode-safe OpenCV image I/O helpers for Windows paths."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


ImagePath = str | Path


def read_image(path: ImagePath, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Read an image with OpenCV while supporting Unicode filesystem paths."""

    image_path = Path(path)
    try:
        buffer = np.fromfile(image_path, dtype=np.uint8)
    except OSError:
        return None
    if buffer.size == 0:
        return None
    return cv2.imdecode(buffer, flags)


def write_image(
    path: ImagePath,
    image: np.ndarray,
    params: list[int] | tuple[int, ...] | None = None,
) -> bool:
    """Write an image with OpenCV while preserving Unicode filesystem paths."""

    image_path = Path(path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = image_path.suffix or '.png'
    encode_params = list(params) if params is not None else []
    success, encoded = cv2.imencode(suffix, image, encode_params)
    if not success:
        return False
    try:
        encoded.tofile(image_path)
    except OSError:
        return False
    return True
