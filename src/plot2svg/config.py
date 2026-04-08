"""Configuration models for the Plot2SVG pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


VALID_ENHANCEMENT_MODES = {"auto", "skip", "light", "sr_x2", "sr_x4"}
VALID_EXECUTION_PROFILES = {"speed", "balanced", "quality"}


@dataclass(slots=True)
class PipelineConfig:
    """Static configuration used to run a single pipeline job."""

    input_path: Path
    output_dir: Path
    route_override: str | None = None
    enhancement_mode: str = "auto"
    execution_profile: str = "balanced"
    enable_sam2: bool = False
    enable_edge_model: bool = False
    tile_size: int = 1024
    ocr_max_workers: int = 0
    enable_shape_detection: bool = True

    def __post_init__(self) -> None:
        self.input_path = Path(self.input_path)
        self.output_dir = Path(self.output_dir)
        if self.enhancement_mode not in VALID_ENHANCEMENT_MODES:
            raise ValueError(f"Unsupported enhancement mode: {self.enhancement_mode}")
        if self.execution_profile not in VALID_EXECUTION_PROFILES:
            raise ValueError(f"Unsupported execution profile: {self.execution_profile}")
        if self.tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if self.ocr_max_workers < 0:
            raise ValueError("ocr_max_workers must be >= 0 (0 = auto)")

    def proposal_max_side(self) -> int:
        if self.execution_profile == "speed":
            return 1400
        if self.execution_profile == "quality":
            return 2400
        return 1800

    def text_skip_min_width(self) -> int:
        if self.execution_profile == "speed":
            return 28
        if self.execution_profile == "quality":
            return 12
        return 18

    def text_skip_min_height(self) -> int:
        if self.execution_profile == "speed":
            return 14
        if self.execution_profile == "quality":
            return 8
        return 10

    def ocr_variant_count(self) -> int:
        if self.execution_profile == "speed":
            return 2
        if self.execution_profile == "quality":
            return 4
        return 3
