import importlib.util
import pathlib
import subprocess
import sys
import unittest




def _load_module():
    sandbox_dir = pathlib.Path(__file__).resolve().parent
    script_path = sandbox_dir / 'sandbox_path_tracing.py'
    spec = importlib.util.spec_from_file_location('sandbox_path_tracing_module', script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SandboxPathTracingTest(unittest.TestCase):
    def test_path_tracing_script_generates_expected_outputs(self) -> None:
        sandbox_dir = pathlib.Path(__file__).resolve().parent
        script_path = sandbox_dir / 'sandbox_path_tracing.py'
        self.assertTrue(script_path.exists(), 'sandbox_path_tracing.py missing')

        outputs = [
            sandbox_dir / 'debug_03_paths.png',
            sandbox_dir / 'slice_A_v2.svg',
        ]
        for output in outputs:
            if output.exists():
                try:
                    output.unlink()
                except PermissionError:
                    pass

        result = subprocess.run(
            [sys.executable, '-X', 'utf8', str(script_path)],
            cwd=str(sandbox_dir.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + '\n' + result.stderr)
        for output in outputs:
            self.assertTrue(output.exists(), f'{output.name} not generated')
            self.assertGreater(output.stat().st_size, 0, f'{output.name} empty')

        svg_text = outputs[-1].read_text(encoding='utf-8')
        self.assertTrue('<polyline ' in svg_text or '<path ' in svg_text)

    def test_simplify_polyline_drops_collinear_points(self) -> None:
        module = _load_module()
        points = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
        simplified = module.simplify_polyline(points, tolerance=0.5)
        self.assertEqual(simplified, [(0, 0), (4, 4)])

    def test_trace_skeleton_to_paths_drops_short_paths(self) -> None:
        module = _load_module()
        skeleton = module.np.zeros((20, 20), dtype=module.np.uint8)
        skeleton[2:7, 2] = 255
        skeleton[10:19, 12] = 255
        paths = module.trace_skeleton_to_paths(skeleton)
        self.assertEqual(len(paths), 1)
        self.assertGreaterEqual(len(paths[0].points), 2)


if __name__ == '__main__':
    unittest.main()
