import unittest

from plot2svg.scene_graph import (
    IconObject,
    RasterObject,
    SceneObject,
    SceneGraph,
    SceneNode,
    SceneRelation,
    build_object_instances,
    build_scene_graph,
    promote_component_groups,
)
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

    def test_scene_graph_serializes_relations(self) -> None:
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[],
            relations=[
                SceneRelation(
                    id="rel-1",
                    relation_type="fan",
                    source_ids=["c1", "c2"],
                    target_ids=["target"],
                    backbone_id="stroke-1",
                    group_id="fan-stroke-1",
                    metadata={"direction": "right"},
                )
            ],
        )

        payload = graph.to_dict()

        self.assertIn("relations", payload)
        self.assertEqual(payload["relations"][0]["relation_type"], "fan")
        self.assertEqual(payload["relations"][0]["backbone_id"], "stroke-1")

    def test_scene_graph_serializes_objects(self) -> None:
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[],
            objects=[
                SceneObject(
                    id="obj-1",
                    object_type="title",
                    bbox=[0, 0, 50, 20],
                    node_ids=["text-1"],
                    metadata={"title_text": "Polygenic"},
                )
            ],
        )

        payload = graph.to_dict()

        self.assertIn("objects", payload)
        self.assertEqual(payload["objects"][0]["object_type"], "title")
        self.assertEqual(payload["objects"][0]["metadata"]["title_text"], "Polygenic")

    def test_scene_graph_serializes_icon_objects(self) -> None:
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[],
            icon_objects=[
                IconObject(
                    id="icon-1",
                    node_id="region-icon",
                    bbox=[10, 12, 40, 44],
                    compound_path="M 10,10 L 20,10 L 20,20 L 10,20 Z M 12,12 L 18,12 L 18,18 L 12,18 Z",
                    fill="#111111",
                    fill_rule="evenodd",
                    metadata={"source": "pipeline"},
                )
            ],
        )

        payload = graph.to_dict()

        self.assertIn("icon_objects", payload)
        self.assertEqual(payload["icon_objects"][0]["fill_rule"], "evenodd")
        self.assertIn("M 10,10", payload["icon_objects"][0]["compound_path"])

    def test_scene_graph_serializes_raster_objects(self) -> None:
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[],
            raster_objects=[
                RasterObject(
                    id="raster-1",
                    node_id="region-icon",
                    bbox=[10, 12, 40, 44],
                    image_href="data:image/png;base64,AAAA",
                    metadata={"source": "pipeline"},
                )
            ],
        )

        payload = graph.to_dict()

        self.assertIn("raster_objects", payload)
        self.assertEqual(payload["raster_objects"][0]["image_href"], "data:image/png;base64,AAAA")

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

    def test_promote_component_groups_creates_connector_group_for_diagonal_stroke(self) -> None:
        graph = SceneGraph(
            width=240,
            height=180,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 240, 180], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="stroke-001", type="stroke", bbox=[40, 40, 104, 82], z_index=1, vector_mode="stroke_path", confidence=0.9),
            ],
        )

        promoted = promote_component_groups(graph)

        connector_groups = [group for group in promoted.groups if group.role == "connector"]
        self.assertEqual(len(connector_groups), 1)
        self.assertEqual(connector_groups[0].child_ids, ["stroke-001"])

    def test_promote_component_groups_preserves_svg_template_role_token(self) -> None:
        graph = SceneGraph(
            width=240,
            height=180,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 240, 180], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="region-001", type="region", bbox=[20, 20, 120, 120], z_index=1, vector_mode="region_path", confidence=0.9, component_role="svg_template:database", shape_hint="svg_template"),
                SceneNode(id="text-001", type="text", bbox=[28, 126, 112, 146], z_index=2, vector_mode="text_box", confidence=0.95, text_content="Data Sources"),
            ],
        )

        promoted = promote_component_groups(graph)
        region_node = next(node for node in promoted.nodes if node.id == "region-001")

        self.assertIn("container_shape", region_node.component_role or "")
        self.assertIn("svg_template:database", region_node.component_role or "")

    def test_build_object_instances_detects_title_and_network_container(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 1200, 800], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-title", type="text", bbox=[40, 20, 180, 44], z_index=1, vector_mode="text_box", confidence=0.95, text_content="Omnigenic"),
                SceneNode(id="region-001", type="region", bbox=[700, 40, 1080, 560], z_index=2, vector_mode="region_path", confidence=0.9),
                SceneNode(id="stroke-001", type="stroke", bbox=[760, 90, 980, 110], z_index=3, vector_mode="stroke_path", confidence=0.8),
                SceneNode(id="stroke-002", type="stroke", bbox=[770, 200, 980, 220], z_index=4, vector_mode="stroke_path", confidence=0.8),
                SceneNode(id="circle-1", type="region", bbox=[760, 120, 790, 150], z_index=5, vector_mode="region_path", confidence=0.8, shape_hint="circle"),
                SceneNode(id="circle-2", type="region", bbox=[920, 260, 950, 290], z_index=6, vector_mode="region_path", confidence=0.8, shape_hint="circle"),
            ],
        )

        object_graph = build_object_instances(graph)

        object_types = {obj.object_type for obj in object_graph.objects}
        self.assertIn("title", object_types)
        self.assertIn("network_container", object_types)
        network_container = next(obj for obj in object_graph.objects if obj.object_type == "network_container")
        self.assertIn("region-001", network_container.node_ids)

    def test_build_object_instances_treats_polygon_nodes_as_network_elements(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 1200, 800], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="region-001", type="region", bbox=[680, 40, 1080, 560], z_index=1, vector_mode="region_path", confidence=0.9),
                SceneNode(id="stroke-001", type="stroke", bbox=[740, 110, 980, 130], z_index=2, vector_mode="stroke_path", confidence=0.8),
                SceneNode(id="text-001", type="text", bbox=[760, 70, 930, 96], z_index=3, vector_mode="text_box", confidence=0.95, text_content="Pathway"),
                SceneNode(id="triangle-1", type="region", bbox=[760, 150, 810, 200], z_index=4, vector_mode="region_path", confidence=0.85, shape_hint="triangle"),
                SceneNode(id="pentagon-1", type="region", bbox=[900, 250, 950, 300], z_index=5, vector_mode="region_path", confidence=0.85, shape_hint="pentagon"),
                SceneNode(id="triangle-2", type="region", bbox=[820, 330, 870, 380], z_index=6, vector_mode="region_path", confidence=0.85, shape_hint="triangle"),
            ],
        )

        object_graph = build_object_instances(graph)

        self.assertTrue(any(obj.object_type == "network_container" for obj in object_graph.objects))


    def test_build_object_instances_promotes_nearby_texts_to_text_cluster(self) -> None:
        graph = SceneGraph(
            width=900,
            height=700,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 900, 700], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-a", type="text", bbox=[120, 180, 292, 224], z_index=1, vector_mode="text_box", confidence=0.95, text_content="Data Sources"),
                SceneNode(id="text-b", type="text", bbox=[121, 433, 297, 470], z_index=2, vector_mode="text_box", confidence=0.95, text_content="Mutation Data"),
                SceneNode(id="text-c", type="text", bbox=[129, 473, 286, 517], z_index=3, vector_mode="text_box", confidence=0.95, text_content="Clinical Data"),
            ],
        )

        object_graph = build_object_instances(graph)

        clusters = [obj for obj in object_graph.objects if obj.object_type == "text_cluster"]
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0].node_ids), {"text-a", "text-b", "text-c"})

    def test_build_object_instances_allows_title_like_text_in_text_cluster(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=1800,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 1200, 1800], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-a", type="text", bbox=[125, 182, 292, 224], z_index=1, vector_mode="text_box", confidence=0.95, text_content="Train Data"),
                SceneNode(id="text-b", type="text", bbox=[121, 433, 297, 470], z_index=2, vector_mode="text_box", confidence=0.95, text_content="Clinical Data"),
                SceneNode(id="text-c", type="text", bbox=[129, 473, 286, 517], z_index=3, vector_mode="text_box", confidence=0.95, text_content="(clin.csv)"),
            ],
        )

        object_graph = build_object_instances(graph)

        titles = [obj for obj in object_graph.objects if obj.object_type == "title"]
        clusters = [obj for obj in object_graph.objects if obj.object_type == "text_cluster"]
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].node_ids, ["text-a"])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(set(clusters[0].node_ids), {"text-a", "text-b", "text-c"})

    def test_build_object_instances_extracts_valid_text_subcluster_from_overconnected_chain(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=1800,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 1200, 1800], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="text-a", type="text", bbox=[125, 182, 292, 224], z_index=1, vector_mode="text_box", confidence=0.95, text_content="Train Data"),
                SceneNode(id="text-b", type="text", bbox=[121, 433, 297, 470], z_index=2, vector_mode="text_box", confidence=0.95, text_content="Clinical Data"),
                SceneNode(id="text-c", type="text", bbox=[129, 473, 286, 517], z_index=3, vector_mode="text_box", confidence=0.95, text_content="(clin.csv)"),
                SceneNode(id="text-d", type="text", bbox=[109, 649, 308, 682], z_index=4, vector_mode="text_box", confidence=0.95, text_content="Mutation Data"),
                SceneNode(id="text-e", type="text", bbox=[62, 689, 356, 725], z_index=5, vector_mode="text_box", confidence=0.95, text_content="(data_mutations.txt)"),
            ],
        )

        object_graph = build_object_instances(graph)

        clusters = [obj for obj in object_graph.objects if obj.object_type == "text_cluster"]
        self.assertTrue(any({"text-a", "text-b", "text-c"}.issubset(set(cluster.node_ids)) for cluster in clusters))

    def test_promote_component_groups_does_not_anchor_title_text_to_large_container_region(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[
                SceneNode(id="background-root", type="background", bbox=[0, 0, 1200, 800], z_index=0, vector_mode="region_path", confidence=1.0),
                SceneNode(id="region-001", type="region", bbox=[700, 40, 1080, 560], z_index=1, vector_mode="region_path", confidence=0.9),
                SceneNode(id="text-title", type="text", bbox=[760, 22, 900, 44], z_index=2, vector_mode="text_box", confidence=0.95, text_content="Omnigenic"),
                SceneNode(id="stroke-001", type="stroke", bbox=[760, 90, 980, 110], z_index=3, vector_mode="stroke_path", confidence=0.8),
                SceneNode(id="circle-1", type="region", bbox=[760, 120, 790, 150], z_index=4, vector_mode="region_path", confidence=0.8, shape_hint="circle"),
                SceneNode(id="circle-2", type="region", bbox=[920, 260, 950, 290], z_index=5, vector_mode="region_path", confidence=0.8, shape_hint="circle"),
            ],
        )

        object_graph = build_object_instances(graph)
        promoted = promote_component_groups(object_graph)

        self.assertFalse(any(group.role == "labeled_region" and "region-001" in group.child_ids and "text-title" in group.child_ids for group in promoted.groups))
        self.assertTrue(any(group.role == "text_label" and group.child_ids == ["text-title"] for group in promoted.groups))

    def test_scene_node_serializes_shape_hint(self) -> None:
        node = SceneNode(
            id="r1", type="region", bbox=[0, 0, 10, 10],
            z_index=1, vector_mode="region_path", confidence=0.9,
            shape_hint="circle",
        )
        self.assertEqual(node.to_dict()["shape_hint"], "circle")

    def test_scene_node_shape_hint_defaults_none(self) -> None:
        node = SceneNode(id="r2", type="region", bbox=[0, 0, 10, 10], z_index=1, vector_mode="region_path", confidence=0.9)
        self.assertIsNone(node.shape_hint)

    def test_build_scene_graph_propagates_shape_hint(self) -> None:
        proposals = [
            ComponentProposal("region-000", [0, 0, 10, 10], "masks/r.png", "region", 0.9, shape_hint="circle"),
        ]
        graph = build_scene_graph(100, 80, proposals)
        region_node = next(n for n in graph.nodes if n.id == "region-000")
        self.assertEqual(region_node.shape_hint, "circle")


if __name__ == "__main__":
    unittest.main()
