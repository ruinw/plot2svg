"""Command-line interface for Plot2SVG."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import PipelineConfig, VALID_EXECUTION_PROFILES, VALID_SEGMENTATION_BACKENDS, VALID_TEMPLATE_OPTIMIZATIONS
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
        "--segmentation-backend",
        default="opencv",
        choices=sorted(VALID_SEGMENTATION_BACKENDS),
        help="Component segmentation backend.",
    )
    parser.add_argument(
        "--template-optimization",
        default="deterministic",
        choices=sorted(VALID_TEMPLATE_OPTIMIZATIONS),
        help="Layout template optimization mode.",
    )
    parser.add_argument(
        "--no-template",
        dest="emit_layout_template",
        action="store_false",
        help="Skip writing template.svg.",
    )
    parser.set_defaults(emit_layout_template=True)
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
        segmentation_backend=args.segmentation_backend,
        template_optimization=args.template_optimization,
        emit_layout_template=args.emit_layout_template,
    )
    artifacts = run_pipeline(config)
    logger.info("analyze=%s", artifacts.analyze_path)
    logger.info("scene_graph=%s", artifacts.scene_graph_path)
    logger.info("final_svg=%s", artifacts.final_svg_path)
    if getattr(artifacts, "components_path", None) is not None:
        logger.info("components=%s", artifacts.components_path)
    if getattr(artifacts, "template_svg_path", None) is not None:
        logger.info("template_svg=%s", artifacts.template_svg_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
