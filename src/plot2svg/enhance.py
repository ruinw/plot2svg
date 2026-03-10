"""Quality enhancement stage for the Plot2SVG pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import cv2
import numpy as np

from .analyze import AnalysisResult
from .config import PipelineConfig
from .gpu import clahe_apply, filter2d, resize


@dataclass(slots=True)
class EnhancementPlan:
    """Selected enhancement strategy for one image."""

    mode: str
    use_super_resolution: bool
    use_tiling: bool

    @classmethod
    def from_route(cls, route_type: str, requested_mode: str) -> "EnhancementPlan":
        if requested_mode != "auto":
            return cls(
                mode=requested_mode,
                use_super_resolution=requested_mode in {"sr_x2", "sr_x4"},
                use_tiling=False,
            )

        if route_type == "wide_hires":
            return cls(mode="light", use_super_resolution=False, use_tiling=True)
        if route_type in {"small_lowres", "signature_lineart"}:
            return cls(mode="sr_x2", use_super_resolution=True, use_tiling=False)
        return cls(mode="light", use_super_resolution=False, use_tiling=False)


@dataclass(slots=True)
class EnhancementResult:
    """Artifacts emitted by the enhancement stage."""

    image_path: Path
    mode: str
    tiled: bool
    scale_factor: float
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["image_path"] = str(self.image_path)
        return data

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def enhance_image(path: Path, analysis: AnalysisResult, cfg: PipelineConfig) -> EnhancementResult:
    """Create an enhanced image artifact and enhancement metadata."""

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    plan = EnhancementPlan.from_route(analysis.route_type, cfg.enhancement_mode)
    input_path = Path(path)
    image = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Failed to read image: {input_path}")

    working = _normalize_image(image)
    notes = [f"route={analysis.route_type}", f"mode={plan.mode}"]

    if plan.mode != "skip":
        working = _light_enhance(working, analysis)
        notes.append("applied_light_enhancement")

    scale_factor = 1.0
    if plan.use_super_resolution:
        scale_factor = 2.0 if plan.mode == "sr_x2" else 4.0 if plan.mode == "sr_x4" else 2.0
        working = _upsample_image(working, scale_factor)
        notes.append(f"upsampled_{int(scale_factor)}x")

    enhanced_path = cfg.output_dir / "enhanced.png"
    cv2.imwrite(str(enhanced_path), working)

    result = EnhancementResult(
        image_path=enhanced_path,
        mode=plan.mode,
        tiled=plan.use_tiling or analysis.should_tile,
        scale_factor=scale_factor,
        notes=notes,
    )
    result.write_json(cfg.output_dir / "enhance.json")
    return result


def _normalize_image(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _light_enhance(image: np.ndarray, analysis: AnalysisResult) -> np.ndarray:
    blurred = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 21)
    lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clip_limit = 3.0 if analysis.route_type == "signature_lineart" else 2.0
    tile_grid = (8, 8) if analysis.route_type == "wide_hires" else (6, 6)
    clahe_result = clahe_apply(l_channel, clip_limit=clip_limit, tile_grid_size=tile_grid)
    merged = cv2.merge((clahe_result, a_channel, b_channel))
    contrast = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = filter2d(contrast, -1, kernel)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _upsample_image(image: np.ndarray, scale_factor: float) -> np.ndarray:
    width = max(int(image.shape[1] * scale_factor), 1)
    height = max(int(image.shape[0] * scale_factor), 1)
    return resize(image, (width, height), interpolation=cv2.INTER_CUBIC)
