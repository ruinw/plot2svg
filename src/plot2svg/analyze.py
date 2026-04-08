"""Input analysis and route selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import numpy as np


@dataclass(slots=True)
class AnalysisResult:
    """Minimal image analysis result used by the pipeline."""

    width: int
    height: int
    aspect_ratio: float
    color_complexity: float
    edge_density: float
    alpha_present: bool
    route_type: str
    should_tile: bool
    should_super_resolve: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def analyze_image(path: Path) -> AnalysisResult:
    """Read the image header and choose an initial routing strategy."""

    image_path = Path(path)
    width, height, alpha_present = _read_image_metadata(image_path)
    aspect_ratio = width / height if height else 0.0
    file_size = image_path.stat().st_size
    pixel_count = max(width * height, 1)

    color_complexity = min(file_size / pixel_count, 1.0)
    edge_density = min((width + height) / pixel_count * 8.0, 1.0)

    route_type = _choose_route(image_path=image_path, width=width, height=height, aspect_ratio=aspect_ratio)
    should_tile = width >= 4096 or height >= 4096 or pixel_count >= 10_000_000
    should_super_resolve = route_type in {"small_lowres", "signature_lineart"} and max(width, height) < 1400

    return AnalysisResult(
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        color_complexity=color_complexity,
        edge_density=edge_density,
        alpha_present=alpha_present,
        route_type=route_type,
        should_tile=should_tile,
        should_super_resolve=should_super_resolve,
    )


def _choose_route(image_path: Path, width: int, height: int, aspect_ratio: float) -> str:
    stem = image_path.stem.lower()
    if ("signature" in stem or "sign" in stem) and _looks_like_signature_lineart(image_path):
        return "signature_lineart"
    if width >= 3000 and aspect_ratio >= 2.4:
        return "wide_hires"
    if max(width, height) <= 900:
        return "small_lowres"
    return "flat_graphics"


def _looks_like_signature_lineart(path: Path) -> bool:
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((256, 256))
        arr = np.asarray(rgb, dtype=np.uint8)

    maxc = arr.max(axis=2).astype(np.float32)
    minc = arr.min(axis=2).astype(np.float32)
    saturation = np.zeros_like(maxc, dtype=np.float32)
    nonzero = maxc > 0
    saturation[nonzero] = (maxc[nonzero] - minc[nonzero]) / maxc[nonzero] * 255.0
    gray = arr.mean(axis=2)
    dark_ratio = float(np.mean(gray < 220))
    p95_saturation = float(np.percentile(saturation, 95))
    return p95_saturation <= 64.0 and dark_ratio <= 0.18


def _read_image_metadata(path: Path) -> tuple[int, int, bool]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            alpha_present = "A" in image.getbands() or "transparency" in image.info
    except UnidentifiedImageError as exc:
        raise ValueError(f"Unsupported image format for {path}") from exc
    return width, height, alpha_present
