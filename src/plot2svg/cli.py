"""Command-line interface for Plot2SVG."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import PipelineConfig, VALID_EXECUTION_PROFILES
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the Plot2SVG CLI parser."""

    parser = argparse.ArgumentParser(description="Convert PNG images into editable SVG artifacts.")
    parser.add_argument("--input", required=True, help="Path to the input PNG image.")
    parser.add_argument("--output", required=True, help="Directory where pipeline outputs will be written.")
    parser.add_argument(
        "--profile",
        default="balanced",
        choices=sorted(VALID_EXECUTION_PROFILES),
        help="Execution profile controlling the speed/quality tradeoff.",
    )
    parser.add_argument(
        "--enhancement-mode",
        default="auto",
        choices=["auto", "skip", "light", "sr_x2", "sr_x4"],
        help="Enhancement mode for the pre-processing stage.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging and debug image output.",
    )
    return parser


def main() -> int:
    """Run the CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s", force=True)
    config = PipelineConfig(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        enhancement_mode=args.enhancement_mode,
        execution_profile=args.profile,
        emit_debug_artifacts=args.verbose,
    )
    artifacts = run_pipeline(config)
    logger.info("analyze=%s", artifacts.analyze_path)
    logger.info("scene_graph=%s", artifacts.scene_graph_path)
    logger.info("final_svg=%s", artifacts.final_svg_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
