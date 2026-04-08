import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest


def _load_module():
    sandbox_dir = pathlib.Path(__file__).resolve().parent
    script_path = sandbox_dir / "sandbox_line_refinement.py"
    spec = importlib.util.spec_from_file_location("sandbox_line_refinement_module", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SandboxLineRefinementTest(unittest.TestCase):
    def test_merge_pair_snaps_nearby_endpoints(self) -> None:
        module = _load_module()
        left = module.PolyPath(
            [
                module.np.array([0.0, 0.0], dtype=module.np.float32),
                module.np.array([10.0, 0.0], dtype=module.np.float32),
            ]
        )
        right = module.PolyPath(
            [
                module.np.array([11.0, 0.5], dtype=module.np.float32),
                module.np.array([20.0, 1.0], dtype=module.np.float32),
            ]
        )
        merged = module.merge_pair(left, right, (False, True))
        self.assertEqual(len(merged.points), 3)
        self.assertAlmostEqual(float(merged.points[1][0]), 10.5, places=3)

    def test_script_generates_outputs_and_reduces_path_count(self) -> None:
        sandbox_dir = pathlib.Path(__file__).resolve().parent
        script_path = sandbox_dir / "sandbox_line_refinement.py"
        outputs = [
            sandbox_dir / "debug_04_refined_structure.png",
            sandbox_dir / "slice_A_v3.svg",
        ]
        for output in outputs:
            if output.exists():
                try:
                    output.unlink()
                except PermissionError:
                    pass

        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script_path)],
            cwd=str(sandbox_dir.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)
        for output in outputs:
            self.assertTrue(output.exists(), f"{output.name} not generated")
            self.assertGreater(output.stat().st_size, 0, f"{output.name} empty")

        svg_text = outputs[-1].read_text(encoding="utf-8")
        path_count = len(re.findall(r"<path ", svg_text))
        self.assertLessEqual(path_count, 30, msg=svg_text)
        self.assertIn("Refined to", result.stdout)


if __name__ == "__main__":
    unittest.main()
