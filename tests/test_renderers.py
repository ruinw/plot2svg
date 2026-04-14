import unittest

from plot2svg.renderers.edge_renderer import render_graph_edge
from plot2svg.renderers.object_renderer import _should_prune_raster_object, render_icon_object, render_node_object, render_raster_object
from plot2svg.renderers.region_renderer import render_region_object
from plot2svg.renderers.text_renderer import render_text_node
from plot2svg.scene_graph import GraphEdge, IconObject, NodeObject, RasterObject, RegionObject, SceneGraph, SceneNode


class RendererModulesTest(unittest.TestCase):
    def test_region_renderer_renders_circle_region(self) -> None:
        scene_graph = SceneGraph(width=220, height=180, nodes=[])
        fragment = render_region_object(
            RegionObject(
                id="region-object-circle",
                node_id="region-circle",
                outer_path="M 0 0 Z",
                holes=[],
                fill="#dde8ff",
                stroke="#556677",
                metadata={"shape_type": "circle", "circle": {"cx": 110.0, "cy": 90.0, "r": 42.0}},
            ),
            scene_graph,
            {},
        )

        self.assertIn("<circle", fragment or "")

    def test_object_renderer_renders_icon_and_raster_fragments(self) -> None:
        icon_fragment = render_icon_object(
            IconObject(
                id="icon-object-1",
                node_id="region-icon-1",
                bbox=[72, 18, 100, 46],
                compound_path="M 72,18 L 100,18 L 100,46 L 72,46 Z",
                fill="#111111",
                fill_rule="evenodd",
            )
        )
        raster_fragment = render_raster_object(
            RasterObject(
                id="raster-icon-1",
                node_id="region-icon-1",
                bbox=[10, 15, 50, 55],
                image_href="data:image/png;base64,AAAA",
            )
        )

        self.assertIn("class='icon-object'", icon_fragment)
        self.assertIn("<image", raster_fragment)

    def test_object_renderer_prunes_small_raster_candidate(self) -> None:
        self.assertTrue(
            _should_prune_raster_object(
                RasterObject(
                    id="raster-noise-1",
                    node_id="region-noise-1",
                    bbox=[10, 15, 34, 39],
                    image_href="data:image/png;base64,AAAA",
                    metadata={"shape_hint": "raster_candidate", "variance": 1800.0},
                )
            )
        )

    def test_edge_renderer_renders_marker_line(self) -> None:
        graph = SceneGraph(width=120, height=80, nodes=[])
        fragments = render_graph_edge(
            GraphEdge(
                id="graph-edge-arrow-defs",
                source_id="node-a",
                target_id="node-b",
                path=[[20.0, 40.0], [100.0, 40.0]],
                arrow_head={"tip": [100.0, 40.0], "left": [90.0, 36.0], "right": [90.0, 44.0]},
            ),
            graph,
            {},
        )

        self.assertEqual(len(fragments), 1)
        self.assertIn("marker-end='url(#standard-arrow)'", fragments[0])

    def test_text_renderer_renders_multiline_tspans(self) -> None:
        fragment = render_text_node(
            SceneNode(
                id="text-multi",
                type="text",
                bbox=[20, 20, 140, 80],
                z_index=1,
                vector_mode="text_box",
                confidence=0.9,
                text_content="HELLO\nWORLD",
                stroke="#000000",
            )
        )

        self.assertIn("<tspan", fragment or "")
