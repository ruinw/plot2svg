import unittest
from unittest.mock import patch

from plot2svg.cli import build_parser, main


class CliTest(unittest.TestCase):
    def test_cli_accepts_execution_profile_argument(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--input", "picture/F2.png", "--output", "outputs/F2", "--profile", "quality"])
        self.assertEqual(args.profile, "quality")

    def test_cli_accepts_segmentation_and_template_options(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--input", "picture/F2.png",
            "--output", "outputs/F2",
            "--segmentation-backend", "opencv",
            "--template-optimization", "none",
            "--no-template",
        ])
        self.assertEqual(args.segmentation_backend, "opencv")
        self.assertEqual(args.template_optimization, "none")
        self.assertFalse(args.emit_layout_template)

    def test_cli_accepts_verbose_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--input", "picture/F2.png", "--output", "outputs/F2", "--verbose"])
        self.assertTrue(args.verbose)

    @patch("plot2svg.cli.run_pipeline")
    def test_cli_passes_template_and_segmentation_options(self, mock_run_pipeline) -> None:
        from types import SimpleNamespace

        captured = {}
        def fake_run_pipeline(config):
            captured['segmentation_backend'] = config.segmentation_backend
            captured['template_optimization'] = config.template_optimization
            captured['emit_layout_template'] = config.emit_layout_template
            return SimpleNamespace(
                analyze_path="outputs/F2/analyze.json",
                scene_graph_path="outputs/F2/scene_graph.json",
                final_svg_path="outputs/F2/final.svg",
                components_path="outputs/F2/components.json",
                template_svg_path=None,
            )

        mock_run_pipeline.side_effect = fake_run_pipeline
        with patch("sys.argv", [
            "plot2svg",
            "--input", "picture/F2.png",
            "--output", "outputs/F2",
            "--segmentation-backend", "opencv",
            "--template-optimization", "none",
            "--no-template",
        ]):
            main()

        self.assertEqual(captured, {
            'segmentation_backend': 'opencv',
            'template_optimization': 'none',
            'emit_layout_template': False,
        })

    @patch("plot2svg.cli.run_pipeline")
    def test_cli_logs_artifact_paths(self, mock_run_pipeline) -> None:
        from types import SimpleNamespace

        mock_run_pipeline.return_value = SimpleNamespace(
            analyze_path="outputs/F2/analyze.json",
            scene_graph_path="outputs/F2/scene_graph.json",
            final_svg_path="outputs/F2/final.svg",
            components_path="outputs/F2/components.json",
            template_svg_path="outputs/F2/template.svg",
        )

        with patch("sys.argv", ["plot2svg", "--input", "picture/F2.png", "--output", "outputs/F2"]):
            with self.assertLogs("plot2svg.cli", level="INFO") as logs:
                exit_code = main()

        self.assertEqual(exit_code, 0)
        joined = "\n".join(logs.output)
        self.assertIn("analyze=", joined)
        self.assertIn("scene_graph=", joined)
        self.assertIn("final_svg=", joined)
        self.assertIn("components=", joined)
        self.assertIn("template_svg=", joined)


if __name__ == "__main__":
    unittest.main()