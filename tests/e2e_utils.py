from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "picture").exists():
            return parent
    raise FileNotFoundError("Could not locate repository root with picture/ directory.")


def source_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate src/ directory for test execution.")


def sample_image_path(image_name: str) -> Path:
    path = repo_root() / "picture" / image_name
    if not path.exists():
        raise FileNotFoundError(f"Sample image not found: {path}")
    return path


def fixtures_root() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def generated_input_root() -> Path:
    path = source_root().parent / "output" / "_phase3_inputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_regression_snapshot() -> dict[str, dict[str, object]]:
    snapshot_path = fixtures_root() / "e2e_regression_snapshot.json"
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def generated_input_path(name: str) -> Path:
    return generated_input_root() / name


def _temp_output_dir(prefix: str) -> Path:
    temp_root = source_root().parent / "output" / "_phase3_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    path = temp_root / f"{prefix}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_pipeline_summary_isolated(image_path: Path) -> dict[str, object]:
    output_dir = _temp_output_dir("phase3-e2e")
    try:
        payload = _run_subprocess_payload(image_path=image_path, output_dir=output_dir)
        return payload["summary"]
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def measure_pipeline_stage_timings(image_path: Path) -> dict[str, float]:
    output_dir = _temp_output_dir("phase3-perf")
    try:
        payload = _run_subprocess_payload(image_path=image_path, output_dir=output_dir)
        return payload["timings"]
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _run_subprocess_payload(*, image_path: Path, output_dir: Path) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source_root())
    script = """
import json
import time
from pathlib import Path
from plot2svg.api import Plot2SvgEngine

image_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
start = time.time()
engine = Plot2SvgEngine()
payload = engine.process_image(image_path=image_path, output_dir=output_dir)

scene_graph = payload.get("scene_graph") or {}
svg_content = payload.get("svg_content") or ""

def count_nodes(node_type):
    return sum(1 for node in scene_graph.get("nodes", []) if node.get("type") == node_type)

def stage_time(name):
    path = output_dir / name
    if not path.exists():
        return None
    return path.stat().st_mtime

analyze_t = stage_time("analyze.json")
enhance_t = stage_time("enhanced.png")
ocr_t = stage_time("debug_text_inpaint.png")
stage1_t = stage_time("debug_nodes_inpaint.png")
stage2_detect_t = stage_time("debug_lines_mask.png")
stage2_t = stage_time("debug_strokes_inpaint.png")
stage3_t = stage_time("debug_region_segmentation.png")
scene_t = stage_time("scene_graph.json")
svg_t = stage_time("final.svg")

def delta(left, right, fallback):
    if left is None or right is None:
        return fallback
    return max(right - left, 0.0)

summary = {
    "status": payload.get("status"),
    "node_count": len(scene_graph.get("nodes", [])),
    "text_count": count_nodes("text"),
    "region_count": count_nodes("region"),
    "stroke_count": count_nodes("stroke"),
    "object_count": len(scene_graph.get("objects", [])),
    "relation_count": len(scene_graph.get("relations", [])),
    "graph_edge_count": len(scene_graph.get("graph_edges", [])),
    "icon_object_count": len(scene_graph.get("icon_objects", [])),
    "raster_object_count": len(scene_graph.get("raster_objects", [])),
    "has_group_tag": "<g" in svg_content,
    "has_shape_data": "data-shape-type" in svg_content,
}

timings = {
    "analyze_sec": delta(start, analyze_t, 0.0),
    "enhance_sec": delta(analyze_t or start, enhance_t, 0.0),
    "ocr_sec": delta(enhance_t or start, ocr_t, 0.0),
    "stage1_sec": delta(ocr_t or start, stage1_t, 0.0),
    "stage2_detect_sec": delta(stage1_t or start, stage2_detect_t, 0.0),
    "stage2_finalize_sec": delta(stage2_detect_t or start, stage2_t, 0.0),
    "stage3_sec": delta(stage2_t or start, stage3_t, 0.0),
    "scene_graph_sec": delta(stage3_t or start, scene_t, 0.0),
    "export_sec": delta(scene_t or start, svg_t, 0.0),
    "total_sec": max(time.time() - start, 0.0),
}

print(json.dumps({"summary": summary, "timings": timings}))
"""
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", "import sys\n" + script, str(image_path), str(output_dir)],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])
