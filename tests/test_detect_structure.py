import unittest

from plot2svg.detect_structure import detect_structures
from plot2svg.export_svg import _shape_attrs
from plot2svg.scene_graph import SceneGraph, SceneGroup, SceneNode


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
