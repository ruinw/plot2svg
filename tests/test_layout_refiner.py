import unittest

from plot2svg.layout_refiner import refine_layout
from plot2svg.scene_graph import GraphEdge, SceneGraph, SceneNode


class LayoutRefinerTest(unittest.TestCase):
    def test_refine_layout_merges_fuzzy_duplicate_text_nodes(self) -> None:
        graph = SceneGraph(
            width=300,
            height=180,
            nodes=[
                SceneNode(id='text-a', type='text', bbox=[40, 40, 160, 62], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Feature Engineering'),
                SceneNode(id='text-b', type='text', bbox=[44, 42, 164, 64], z_index=2, vector_mode='text_box', confidence=0.88, text_content='Feature Enginering'),
            ],
        )

        refined = refine_layout(graph)

        text_nodes = [node for node in refined.nodes if node.type == 'text']
        self.assertEqual(len(text_nodes), 1)
        self.assertIn('Feature Engineering', text_nodes[0].text_content or '')

    def test_refine_layout_nudges_overlapping_text_and_updates_edge_endpoint(self) -> None:
        graph = SceneGraph(
            width=320,
            height=220,
            nodes=[
                SceneNode(id='text-top', type='text', bbox=[60, 60, 150, 82], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Top Label'),
                SceneNode(id='text-bottom', type='text', bbox=[64, 70, 170, 92], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Bottom Label'),
            ],
            graph_edges=[
                GraphEdge(
                    id='edge-text-bottom',
                    source_id='object-left',
                    target_id='text-bottom',
                    path=[[20.0, 81.0], [64.0, 81.0]],
                )
            ],
        )

        refined = refine_layout(graph)

        node_map = {node.id: node for node in refined.nodes}
        self.assertGreater(node_map['text-bottom'].bbox[1], 70)
        edge = refined.graph_edges[0]
        self.assertEqual(edge.target_id, 'text-bottom')
        self.assertEqual(edge.path[-1][0], float(node_map['text-bottom'].bbox[0]))
        self.assertGreaterEqual(edge.path[-1][1], float(node_map['text-bottom'].bbox[1]))
        self.assertLessEqual(edge.path[-1][1], float(node_map['text-bottom'].bbox[3]))


if __name__ == "__main__":
    unittest.main()
