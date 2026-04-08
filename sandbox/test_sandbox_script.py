import importlib.util
import pathlib
import subprocess
import sys
import unittest


class SandboxScriptTest(unittest.TestCase):
    def test_script_generates_debug_outputs(self) -> None:
        sandbox_dir = pathlib.Path(__file__).resolve().parent
        script_path = sandbox_dir / 'sandbox_test.py'
        self.assertTrue(script_path.exists(), 'sandbox_test.py missing')

        for name in [
            'debug_01_grayscale.png',
            'debug_02_binary_mask.png',
            'debug_03_morphology.png',
            'debug_04_contours.png',
            'slice_result.svg',
        ]:
            target = sandbox_dir / name
            if target.exists():
                try:
                    target.unlink()
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
        for name in [
            'debug_01_grayscale.png',
            'debug_02_binary_mask.png',
            'debug_03_morphology.png',
            'debug_04_contours.png',
            'slice_result.svg',
        ]:
            target = sandbox_dir / name
            self.assertTrue(target.exists(), f'{name} not generated')
            self.assertGreater(target.stat().st_size, 0, f'{name} is empty')


if __name__ == '__main__':
    unittest.main()
