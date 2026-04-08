from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2


MODULE_PATH = Path(__file__).resolve().parent / "sandbox_line_fix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sandbox_line_fix", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_radial_lines_track_detected_source_nodes() -> None:
    module = load_module()
    image = module.load_image(module.resolve_input_path())
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = module.adaptive_binary(gray)
    skeleton = module.thin_mask(binary)
    circles = module.detect_source_nodes(image)
    hub = module.detect_target_hub(image)
    raw_lines, merged_lines, reconstructed_hub = module.reconstruct_lines(image, skeleton)
    assert len(circles) >= 18, f"expected to detect at least 18 source circles, got {len(circles)}"
    assert len(merged_lines) >= len(circles) - 2, (
        f"expected merged radial lines to stay close to circle count, got {len(merged_lines)} lines "
        f"for {len(circles)} circles"
    )
    assert 105 <= hub[0] <= 120, f"expected hub x near the original right-side node, got {hub[0]}"
    assert abs(reconstructed_hub[0] - hub[0]) <= 3, (
        f"expected reconstructed hub to stay near detected hub, got {reconstructed_hub}"
    )
