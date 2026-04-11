import unittest

from plot2svg.config import PipelineConfig, ThresholdConfig
from plot2svg.detect_structure import detect_structures
from plot2svg.export_svg import _shape_attrs
from plot2svg.scene_graph import SceneGraph, SceneGroup, SceneNode, SceneObject


def _make_graph(
    nodes: list[SceneNode],
    groups: list[SceneGroup],
    width: int = 800,
    height: int = 600,
) -> SceneGraph:
    return SceneGraph(width=width, height=height, nodes=nodes, groups=groups)


class BoxClassificationTest(unittest.TestCase):
    def test_labeled_region_with_text_classified_as_box(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r1", type="region", bbox=[10, 10, 200, 100], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[30, 30, 180, 60], z_index=2, vector_mode="text_box", confidence=0.9, text_content="Box A"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[10, 10, 200, 100], child_ids=["r1", "t1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        self.assertEqual(result.groups[0].shape_type, "box")

    def test_high_aspect_region_not_classified_as_box(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r1", type="region", bbox=[10, 10, 700, 25], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[20, 12, 100, 23], z_index=2, vector_mode="text_box", confidence=0.9, text_content="Label"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[10, 10, 700, 25], child_ids=["r1", "t1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        self.assertIsNone(result.groups[0].shape_type)

    def test_box_classification_respects_custom_aspect_threshold(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r1", type="region", bbox=[10, 10, 700, 25], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[20, 12, 100, 23], z_index=2, vector_mode="text_box", confidence=0.9, text_content="Label"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[10, 10, 700, 25], child_ids=["r1", "t1"]),
        ]
        cfg = PipelineConfig(
            input_path="picture/F2.png",
            output_dir="outputs/F2",
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                detect_structure_box_aspect_max=100.0,
                detect_structure_box_min_side=10,
            ),
        )

        result = detect_structures(_make_graph(nodes, groups), cfg=cfg)
        self.assertEqual(result.groups[0].shape_type, "box")

    def test_network_container_object_not_classified_as_box(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 1600, 900], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r1", type="region", bbox=[900, 60, 1260, 620], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[960, 80, 1100, 110], z_index=2, vector_mode="text_box", confidence=0.9, text_content="Omnigenic"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[900, 60, 1260, 620], child_ids=["r1", "t1"]),
        ]
        objects = [
            SceneObject(
                id="obj-r1",
                object_type="network_container",
                bbox=[900, 60, 1260, 620],
                node_ids=["r1", "t1"],
                metadata={"box_like": False},
            )
        ]
        result = detect_structures(SceneGraph(width=1600, height=900, nodes=nodes, groups=groups, objects=objects))
        self.assertIsNone(result.groups[0].shape_type)


class ArrowClassificationTest(unittest.TestCase):
    def test_horizontal_connector_classified_as_right_arrow(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="s1", type="stroke", bbox=[100, 200, 400, 210], z_index=1, vector_mode="stroke_path", confidence=0.8),
        ]
        groups = [
            SceneGroup(id="c1", role="connector", bbox=[100, 200, 400, 210], child_ids=["s1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        self.assertEqual(result.groups[0].shape_type, "arrow")
        self.assertEqual(result.groups[0].direction, "right")

    def test_arrow_classification_respects_custom_aspect_threshold(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="s1", type="stroke", bbox=[100, 200, 400, 210], z_index=1, vector_mode="stroke_path", confidence=0.8),
        ]
        groups = [
            SceneGroup(id="c1", role="connector", bbox=[100, 200, 400, 210], child_ids=["s1"]),
        ]
        cfg = PipelineConfig(
            input_path="picture/F2.png",
            output_dir="outputs/F2",
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                detect_structure_arrow_aspect_ratio=100.0,
            ),
        )

        result = detect_structures(_make_graph(nodes, groups), cfg=cfg)
        self.assertEqual(result.groups[0].shape_type, "arrow")
        self.assertIsNone(result.groups[0].direction)

    def test_vertical_connector_classified_as_down_arrow(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="s1", type="stroke", bbox=[200, 50, 210, 350], z_index=1, vector_mode="stroke_path", confidence=0.8),
        ]
        groups = [
            SceneGroup(id="c1", role="connector", bbox=[200, 50, 210, 350], child_ids=["s1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        self.assertEqual(result.groups[0].shape_type, "arrow")
        self.assertEqual(result.groups[0].direction, "down")

    def test_connector_group_emits_connector_relation(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="source", type="region", bbox=[60, 220, 140, 280], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="target", type="region", bbox=[320, 220, 400, 280], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="s1", type="stroke", bbox=[130, 225, 330, 275], z_index=3, vector_mode="stroke_path", confidence=0.8),
        ]
        groups = [
            SceneGroup(id="c1", role="connector", bbox=[130, 225, 330, 275], child_ids=["s1"]),
        ]

        result = detect_structures(_make_graph(nodes, groups))

        connector_relations = [relation for relation in result.relations if relation.relation_type == "connector"]
        self.assertEqual(len(connector_relations), 1)
        self.assertEqual(connector_relations[0].group_id, "c1")
        self.assertEqual(connector_relations[0].backbone_id, "s1")
        self.assertEqual(connector_relations[0].source_ids, ["source"])
        self.assertEqual(connector_relations[0].target_ids, ["target"])


class ContainerDetectionTest(unittest.TestCase):
    def test_large_region_containing_two_groups_becomes_container(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r-big", type="region", bbox=[5, 5, 500, 400], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="r1", type="region", bbox=[20, 20, 200, 100], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[30, 30, 180, 60], z_index=3, vector_mode="text_box", confidence=0.9, text_content="A"),
            SceneNode(id="r2", type="region", bbox=[220, 20, 400, 100], z_index=4, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t2", type="text", bbox=[230, 30, 380, 60], z_index=5, vector_mode="text_box", confidence=0.9, text_content="B"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[20, 20, 200, 100], child_ids=["r1", "t1"]),
            SceneGroup(id="g2", role="labeled_region", bbox=[220, 20, 400, 100], child_ids=["r2", "t2"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        containers = [g for g in result.groups if g.role == "container"]
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0].shape_type, "container")
        self.assertIn("g1", containers[0].contains_group_ids)
        self.assertIn("g2", containers[0].contains_group_ids)

    def test_region_containing_only_one_group_not_promoted(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r-big", type="region", bbox=[5, 5, 500, 400], z_index=1, vector_mode="region_path", confidence=0.9),
            SceneNode(id="r1", type="region", bbox=[20, 20, 200, 100], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[30, 30, 180, 60], z_index=3, vector_mode="text_box", confidence=0.9, text_content="A"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[20, 20, 200, 100], child_ids=["r1", "t1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        containers = [g for g in result.groups if g.role == "container"]
        self.assertEqual(len(containers), 0)

    def test_container_detection_preserves_svg_template_role_token(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="r-big", type="region", bbox=[5, 5, 620, 420], z_index=1, vector_mode="region_path", confidence=0.9, component_role="svg_template:database", shape_hint="svg_template"),
            SceneNode(id="r1", type="region", bbox=[20, 20, 200, 100], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t1", type="text", bbox=[30, 30, 180, 60], z_index=3, vector_mode="text_box", confidence=0.9, text_content="A"),
            SceneNode(id="r2", type="region", bbox=[220, 20, 400, 100], z_index=4, vector_mode="region_path", confidence=0.9),
            SceneNode(id="t2", type="text", bbox=[230, 30, 380, 60], z_index=5, vector_mode="text_box", confidence=0.9, text_content="B"),
        ]
        groups = [
            SceneGroup(id="g1", role="labeled_region", bbox=[20, 20, 200, 100], child_ids=["r1", "t1"]),
            SceneGroup(id="g2", role="labeled_region", bbox=[220, 20, 400, 100], child_ids=["r2", "t2"]),
        ]

        result = detect_structures(_make_graph(nodes, groups))
        region_node = next(node for node in result.nodes if node.id == "r-big")

        self.assertEqual(region_node.group_id, "container-r-big")
        self.assertIn("container_boundary", region_node.component_role or "")
        self.assertIn("svg_template:database", region_node.component_role or "")


class FanDetectionTest(unittest.TestCase):
    def test_tall_stroke_with_aligned_circle_sources_and_target_region_becomes_fan(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="stroke-fan", type="stroke", bbox=[20, 80, 150, 520], z_index=1, vector_mode="stroke_path", confidence=0.9),
            SceneNode(id="target", type="region", bbox=[180, 280, 320, 340], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="c1", type="region", bbox=[22, 90, 42, 110], z_index=3, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c2", type="region", bbox=[22, 150, 42, 170], z_index=4, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c3", type="region", bbox=[22, 210, 42, 230], z_index=5, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c4", type="region", bbox=[22, 270, 42, 290], z_index=6, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c5", type="region", bbox=[22, 330, 42, 350], z_index=7, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
        ]
        result = detect_structures(_make_graph(nodes, groups=[]))
        fans = [g for g in result.groups if g.role == "fan"]
        self.assertEqual(len(fans), 1)
        self.assertEqual(fans[0].shape_type, "fan")
        self.assertIn("stroke-fan", fans[0].child_ids)
        self.assertIn("target", fans[0].child_ids)
        fan_relations = [relation for relation in result.relations if relation.relation_type == "fan"]
        self.assertEqual(len(fan_relations), 1)
        self.assertEqual(fan_relations[0].backbone_id, "stroke-fan")
        self.assertEqual(fan_relations[0].target_ids, ["target"])
        self.assertEqual(fan_relations[0].group_id, fans[0].id)
        self.assertEqual(fan_relations[0].source_ids, ["c1", "c2", "c3", "c4", "c5"])

    def test_fan_detection_respects_custom_min_source_count(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="stroke-fan", type="stroke", bbox=[20, 80, 150, 520], z_index=1, vector_mode="stroke_path", confidence=0.9),
            SceneNode(id="target", type="region", bbox=[180, 280, 320, 340], z_index=2, vector_mode="region_path", confidence=0.9),
            SceneNode(id="c1", type="region", bbox=[22, 90, 42, 110], z_index=3, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c2", type="region", bbox=[22, 150, 42, 170], z_index=4, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
            SceneNode(id="c3", type="region", bbox=[22, 210, 42, 230], z_index=5, vector_mode="region_path", confidence=0.9, shape_hint="circle"),
        ]
        cfg = PipelineConfig(
            input_path="picture/F2.png",
            output_dir="outputs/F2",
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=15.0,
                graph_monster_stroke_wide_area_ratio=0.10,
                graph_monster_stroke_area_ratio=0.15,
                graph_monster_stroke_diagonal_ratio=0.50,
                graph_monster_stroke_diagonal_width=6.0,
                detect_structure_fan_min_source_count=3,
            ),
        )

        result = detect_structures(_make_graph(nodes, groups=[]), cfg=cfg)
        fans = [g for g in result.groups if g.role == "fan"]
        self.assertEqual(len(fans), 1)


class RegressionTest(unittest.TestCase):
    def test_existing_groups_preserved(self) -> None:
        nodes = [
            SceneNode(id="bg", type="background", bbox=[0, 0, 800, 600], z_index=0, vector_mode="region_path", confidence=1.0),
            SceneNode(id="t1", type="text", bbox=[50, 50, 150, 70], z_index=1, vector_mode="text_box", confidence=0.9, text_content="Solo"),
        ]
        groups = [
            SceneGroup(id="g1", role="text_label", bbox=[50, 50, 150, 70], child_ids=["t1"]),
        ]
        result = detect_structures(_make_graph(nodes, groups))
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].id, "g1")
        self.assertEqual(result.groups[0].role, "text_label")


class SvgShapeAttrsTest(unittest.TestCase):
    def test_shape_attrs_includes_data_attributes(self) -> None:
        group = SceneGroup(id="g1", role="connector", bbox=[0, 0, 100, 10], child_ids=["s1"], shape_type="arrow", direction="right")
        attrs = _shape_attrs(group)
        self.assertIn("data-shape-type='arrow'", attrs)
        self.assertIn("data-direction='right'", attrs)

    def test_shape_attrs_empty_when_no_shape(self) -> None:
        group = SceneGroup(id="g1", role="text_label", bbox=[0, 0, 100, 20], child_ids=["t1"])
        attrs = _shape_attrs(group)
        self.assertEqual(attrs, "")


if __name__ == "__main__":
    unittest.main()
