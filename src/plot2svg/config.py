"""Configuration models for the Plot2SVG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
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
    graph_partial_repair_min_length: float = 60.0
    graph_unanchored_fragment_min_length: float = 90.0
    graph_partial_anchor_gap: float = 80.0
    graph_partial_general_min_length: float = 110.0
    graph_text_cluster_overlap_ratio: float = 0.55
    graph_text_cluster_vertical_gap: float = 24.0
    graph_one_sided_anchor_gap: float = 80.0
    graph_one_sided_min_length: float = 180.0
    graph_direct_snap_node_radius_mult: float = 2.2
    graph_direct_snap_node_min: float = 24.0
    graph_direct_snap_other_radius_mult: float = 1.1
    graph_direct_snap_other_min: float = 48.0
    graph_gap_snap_node_radius_mult: float = 1.5
    graph_gap_snap_node_min: float = 16.0
    graph_gap_snap_text_radius_mult: float = 0.45
    graph_gap_snap_text_max: float = 28.0
    graph_gap_snap_text_min: float = 14.0
    graph_gap_snap_other_radius_mult: float = 0.28
    graph_gap_snap_other_max: float = 44.0
    graph_gap_snap_other_min: float = 18.0
    graph_gap_candidate_center_distance_weight: float = 0.03
    graph_directional_alignment_min: float = 0.72
    graph_directional_node_hard_cap_mult: float = 3.2
    graph_directional_node_hard_cap_min: float = 42.0
    graph_directional_node_aligned_hard_cap_mult: float = 8.0
    graph_directional_node_aligned_hard_cap_min: float = 96.0
    graph_directional_other_hard_cap_mult: float = 1.8
    graph_directional_other_hard_cap_min: float = 60.0
    graph_directional_other_aligned_hard_cap_mult: float = 2.4
    graph_directional_other_aligned_hard_cap_min: float = 72.0
    graph_directional_node_lateral_cap_mult: float = 2.4
    graph_directional_node_lateral_cap_min: float = 22.0
    graph_directional_other_lateral_cap_mult: float = 2.6
    graph_directional_other_lateral_cap_min: float = 36.0
    graph_directional_center_distance_weight: float = 0.05
    graph_directional_alignment_bonus: float = 10.0
    graph_ray_extension_node_mult: float = 2.0
    graph_ray_extension_node_min: float = 30.0
    graph_ray_extension_text_limit: float = 52.0
    graph_ray_extension_other_mult: float = 0.35
    graph_ray_extension_other_max: float = 54.0
    graph_ray_extension_other_min: float = 36.0


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
    for field_info in fields(thresholds):
        field_name = field_info.name
        value = getattr(thresholds, field_name)
        if value <= 0:
            raise ValueError(f"{field_name} must be positive")
