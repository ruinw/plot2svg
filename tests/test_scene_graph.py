import unittest

from plot2svg.scene_graph import SceneGraph, SceneNode, build_scene_graph, promote_component_groups
from plot2svg.segment import ComponentProposal


class SceneGraphTest(unittest.TestCase):
    def test_scene_node_serializes_vector_mode(self) -> None:
        node = SceneNode(id="n1", type="region", bbox=[0, 0, 10, 10], z_index=1, vector_mode="region_path", confidence=0.9)
        self.assertEqual(node.to_dict()["vector_mode"], "region_path")

    def test_scene_node_serializes_text_content(self) -> None:
        node = SceneNode(id="t1", type="text", bbox=[0, 0, 10, 10], z_index=1, vector_mode="text_box", confidence=0.9, text_content="ABC")
        self.assertEqual(node.to_dict()["text_content"], "ABC")

    def test_scene_graph_tracks_canvas_size(self) -> None:
        graph = SceneGraph(width=100, height=80, nodes=[])
        self.assertEqual(graph.width, 100)
        self.assertEqual(graph.height, 80)

    def test_build_scene_graph_adds_background_root(self) -> None:
        proposals = [
            ComponentProposal("region-000", [0, 0, 10, 10], "masks/r.png", "region", 0.9),
            ComponentProposal("text-001", [10, 10, 40, 20], "masks/t.png", "text_like", 0.8),
        ]
        graph = build_scene_graph(100, 80, proposals)
        self.assertEqual(graph.nodes[0].type, "background")
        self.assertTrue(any(node.type == "text" for node in graph.nodes))

    def test_promote_component_groups_creates_labeled_region_group(self) -> None:
        graph = SceneGraph(
            width=200,
            height=160,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 200, 160], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="region-001", type="region", bbox=[20, 20, 150, 100], z_index=1, vector_mode="region_path", confidence=0.9),
                SceneNode(id="stroke-001", type="stroke", bbox=[18, 18, 152, 22], z_index=2, vector_mode="stroke_path", confidence=0.8),
                SceneNode(id="text-001", type="text", bbox=[50, 45, 120, 70], z_index=3, vector_mode="text_box", confidence=0.95, text_content="LABEL"),
            ],
        )

        promoted = promote_component_groups(graph)

        self.assertEqual(len(promoted.groups), 1)
        self.assertEqual(promoted.groups[0].role, "labeled_region")
        self.assertEqual(set(promoted.groups[0].child_ids), {"region-001", "stroke-001", "text-001"})
        grouped_text = next(node for node in promoted.nodes if node.id == "text-001")
        self.assertEqual(grouped_text.component_role, "label_text")
        self.assertIsNotNone(grouped_text.group_id)


if __name__ == "__main__":
    unittest.main()
