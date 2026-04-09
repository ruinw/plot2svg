"""Configuration models for the Plot2SVG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


VALID_ENHANCEMENT_MODES = {"auto", "skip", "light", "sr_x2", "sr_x4"}
VALID_EXECUTION_PROFILES = {"speed", "balanced", "quality"}


@dataclass(slots=True)
class ThresholdConfig:
    """Profile-aware threshold values used by pipeline submodules."""

    graph_monster_stroke_width: float = 15.0
    graph_monster_stroke_wide_area_ratio: float = 0.10
    graph_monster_stroke_area_ratio: float = 0.15
    graph_monster_stroke_diagonal_ratio: float = 0.50
    graph_monster_stroke_diagonal_width: float = 6.0


_PROFILE_THRESHOLD_OVERRIDES = {
    "speed": {
        "graph_monster_stroke_width": 14.0,
        "graph_monster_stroke_wide_area_ratio": 0.08,
        "graph_monster_stroke_area_ratio": 0.12,
        "graph_monster_stroke_diagonal_ratio": 0.45,
        "graph_monster_stroke_diagonal_width": 5.0,
    },
    "quality": {
        "graph_monster_stroke_width": 17.0,
        "graph_monster_stroke_wide_area_ratio": 0.12,
        "graph_monster_stroke_area_ratio": 0.18,
        "graph_monster_stroke_diagonal_ratio": 0.55,
        "graph_monster_stroke_diagonal_width": 7.0,
    },
}


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
    thresholds: ThresholdConfig | None = None

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
        if self.thresholds is None:
            self.thresholds = _thresholds_for_profile(self.execution_profile)
        _validate_thresholds(self.thresholds)

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


def _thresholds_for_profile(profile: str) -> ThresholdConfig:
    """Build the threshold configuration for an execution profile."""
    overrides = _PROFILE_THRESHOLD_OVERRIDES.get(profile, {})
    return replace(ThresholdConfig(), **overrides)


def _validate_thresholds(thresholds: ThresholdConfig) -> None:
    """Validate threshold values."""
    if thresholds.graph_monster_stroke_width <= 0:
        raise ValueError("graph_monster_stroke_width must be positive")
    if thresholds.graph_monster_stroke_wide_area_ratio <= 0:
        raise ValueError("graph_monster_stroke_wide_area_ratio must be positive")
    if thresholds.graph_monster_stroke_area_ratio <= 0:
        raise ValueError("graph_monster_stroke_area_ratio must be positive")
    if thresholds.graph_monster_stroke_diagonal_ratio <= 0:
        raise ValueError("graph_monster_stroke_diagonal_ratio must be positive")
    if thresholds.graph_monster_stroke_diagonal_width <= 0:
        raise ValueError("graph_monster_stroke_diagonal_width must be positive")
