from pathlib import Path
import unittest

from plot2svg.export_svg import build_svg_group_id, export_svg
from plot2svg.scene_graph import SceneGraph, SceneGroup, SceneNode
from plot2svg.vectorize_region import RegionVectorResult
from plot2svg.vectorize_stroke import StrokeVectorResult


class ExportSvgTest(unittest.TestCase):
    def test_svg_group_ids_are_stable(self) -> None:
        self.assertEqual(build_svg_group_id("component-1"), "component-1")

    def test_export_svg_writes_final_svg(self) -> None:
        output_dir = Path("outputs/test-export")
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 100, 80], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="region-1", type="region", bbox=[0, 0, 10, 10], z_index=1, vector_mode="region_path", confidence=0.9, group_id="component-region-1", component_role="container_shape"),
                SceneNode(id="stroke-1", type="stroke", bbox=[0, 0, 10, 10], z_index=2, vector_mode="stroke_path", confidence=0.9),
                SceneNode(id="text-1", type="text", bbox=[10, 10, 60, 30], z_index=3, vector_mode="text_box", confidence=0.9, text_content="LABEL", group_id="component-region-1", component_role="label_text"),
            ],
            groups=[
                SceneGroup(
                    id="component-region-1",
                    role="labeled_region",
                    bbox=[0, 0, 60, 30],
                    child_ids=["region-1", "text-1"],
                )
            ],
        )
        export_result = export_svg(
            graph,
            [RegionVectorResult(component_id="region-1", svg_fragment="<path id='region-1' />", path_count=1, simplified=False)],
            [StrokeVectorResult(component_id="stroke-1", svg_fragment="M 0 0 C 1 1 2 2 3 3", curve_count=1)],
            output_dir,
        )
        self.assertTrue(export_result.svg_path.exists())
        self.assertTrue(export_result.preview_path.exists())
        self.assertGreater(export_result.preview_path.stat().st_size, 0)
        self.assertEqual(export_result.group_count, 2)
        svg_content = export_result.svg_path.read_text(encoding="utf-8")
        self.assertIn("<text", svg_content)
        self.assertIn("data-component-role='labeled_region'", svg_content)


if __name__ == "__main__":
    unittest.main()
