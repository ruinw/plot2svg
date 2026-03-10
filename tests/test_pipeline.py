from pathlib import Path
import json
import unittest

from plot2svg.config import PipelineConfig
from plot2svg.pipeline import run_pipeline


class PipelineTest(unittest.TestCase):
    def test_run_pipeline_returns_artifact_paths(self) -> None:
        config = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"))
        artifacts = run_pipeline(config)
        self.assertEqual(artifacts.analyze_path.name, "analyze.json")
        self.assertEqual(artifacts.enhanced_path.name, "enhanced.png")
        self.assertEqual(artifacts.scene_graph_path.name, "scene_graph.json")
        self.assertEqual(artifacts.final_svg_path.name, "final.svg")
        data = json.loads(artifacts.scene_graph_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["nodes"]), 2)
        self.assertLess(len(data["nodes"]), 300)
        self.assertTrue(any(node["type"] == "region" for node in data["nodes"]))
        self.assertTrue(any(node["type"] == "stroke" for node in data["nodes"]))


if __name__ == "__main__":
    unittest.main()
