import pathlib
import subprocess
import sys
import unittest


class SandboxDenseLinesTest(unittest.TestCase):
    def test_dense_lines_script_generates_expected_outputs(self) -> None:
        sandbox_dir = pathlib.Path(__file__).resolve().parent
        script_path = sandbox_dir / 'sandbox_dense_lines.py'
        self.assertTrue(script_path.exists(), 'sandbox_dense_lines.py missing')

        outputs = [
            sandbox_dir / 'debug_01_skeleton.png',
            sandbox_dir / 'debug_02_extracted_lines.png',
            sandbox_dir / 'slice_A.svg',
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
        self.assertIn('<line ', svg_text)


if __name__ == '__main__':
    unittest.main()
