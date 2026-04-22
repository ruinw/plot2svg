import unittest

from plot2svg.component_manifest import build_component_manifest
from plot2svg.layout_template import build_layout_template_svg
from plot2svg.scene_graph import SceneGraph, SceneNode


class LayoutTemplateTest(unittest.TestCase):
    def test_build_layout_template_svg_uses_manifest_placeholder_ids(self) -> None:
        graph = SceneGraph(
            width=120,
            height=80,
            nodes=[
                SceneNode(id='text-1', type='text', bbox=[10, 12, 50, 30], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Label'),
                SceneNode(id='region-1', type='region', bbox=[60, 20, 100, 55], z_index=2, vector_mode='region_path', confidence=0.8),
            ],
        )
        manifest = build_component_manifest(graph)

        svg = build_layout_template_svg(manifest)

        self.assertIn("width='120'", svg)
        self.assertIn("height='80'", svg)
        self.assertIn("viewBox='0 0 120 80'", svg)
        for entry in manifest['components']:
            self.assertIn(f"id='{entry['template_id']}'", svg)
            self.assertIn(entry['display_id'], svg)
        self.assertIn("class='template-placeholder", svg)


if __name__ == '__main__':
    unittest.main()