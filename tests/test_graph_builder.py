import unittest

from plot2svg.config import PipelineConfig, ThresholdConfig
from plot2svg.graph_builder import _dedupe_graph_edges, _populate_router_obstacles, build_graph
from plot2svg.router import FlowchartRouter
from plot2svg.scene_graph import GraphEdge, IconObject, NodeObject, SceneGraph, SceneNode, SceneObject, StrokePrimitive


class GraphBuilderTest(unittest.TestCase):
    def test_build_graph_anchors_edge_to_nodes(self) -> None:
        graph = SceneGraph(
            width=200,
            height=100,
            nodes=[],
            node_objects=[
                NodeObject(id="node-a", node_id="region-a", center=[40.0, 50.0], radius=12.0, fill="#336699"),
                NodeObject(id="node-b", node_id="region-b", center=[160.0, 50.0], radius=12.0, fill="#336699"),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id="stroke-primitive-1",
                    node_id="stroke-1",
                    points=[[42.0, 50.0], [100.0, 50.0], [158.0, 50.0]],
                    width=3.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].source_id, "node-a")
        self.assertEqual(updated.graph_edges[0].target_id, "node-b")
        self.assertEqual(len(updated.relations), 1)
        self.assertEqual(updated.relations[0].relation_type, "connector")



    def test_build_graph_keeps_unique_edge_ids_for_multi_primitive_stroke(self) -> None:
        graph = SceneGraph(
            width=240,
            height=120,
            nodes=[],
            node_objects=[
                NodeObject(id='node-a', node_id='region-a', center=[30.0, 60.0], radius=10.0, fill='#336699'),
                NodeObject(id='node-b', node_id='region-b', center=[210.0, 60.0], radius=10.0, fill='#336699'),
            ],
            stroke_primitives=[
                StrokePrimitive(id='stroke-primitive-stroke-1-01', node_id='stroke-1', points=[[40.0, 40.0], [180.0, 40.0]], width=2.0),
                StrokePrimitive(id='stroke-primitive-stroke-1-02', node_id='stroke-1', points=[[40.0, 80.0], [180.0, 80.0]], width=2.0),
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 2)
        self.assertEqual(len({edge.id for edge in updated.graph_edges}), 2)
        self.assertTrue(all(edge.backbone_id == 'stroke-1' for edge in updated.graph_edges))


    def test_build_graph_relaxes_endpoint_snap_radius_for_near_miss(self) -> None:
        graph = SceneGraph(
            width=220,
            height=120,
            nodes=[],
            node_objects=[
                NodeObject(id="node-a", node_id="region-a", center=[40.0, 60.0], radius=10.0, fill="#336699"),
                NodeObject(id="node-b", node_id="region-b", center=[160.0, 60.0], radius=10.0, fill="#336699"),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id="stroke-primitive-near-miss",
                    node_id="stroke-near-miss",
                    points=[[22.0, 60.0], [100.0, 60.0], [144.0, 60.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges[0].source_id, "node-a")
        self.assertEqual(updated.graph_edges[0].target_id, "node-b")

    def test_build_graph_directionally_snaps_line_that_stops_short_of_nodes(self) -> None:
        graph = SceneGraph(
            width=240,
            height=120,
            nodes=[],
            node_objects=[
                NodeObject(id="node-a", node_id="region-a", center=[20.0, 60.0], radius=10.0, fill="#336699"),
                NodeObject(id="node-b", node_id="region-b", center=[180.0, 60.0], radius=10.0, fill="#336699"),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id="stroke-primitive-stop-short",
                    node_id="stroke-stop-short",
                    points=[[50.0, 60.0], [100.0, 60.0], [150.0, 60.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges[0].source_id, "node-a")
        self.assertEqual(updated.graph_edges[0].target_id, "node-b")
        self.assertEqual(len(updated.relations), 1)
        self.assertEqual(updated.relations[0].source_ids, ["node-a"])
        self.assertEqual(updated.relations[0].target_ids, ["node-b"])

    def test_build_graph_repairs_long_partial_edge_to_network_container(self) -> None:
        graph = SceneGraph(
            width=800,
            height=300,
            nodes=[],
            objects=[
                SceneObject(id='object-left', object_type='network_container', bbox=[40, 80, 180, 220], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[520, 80, 720, 220], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-long-partial',
                    node_id='stroke-long-partial',
                    points=[[192.0, 210.0], [300.0, 210.0], [420.0, 210.0], [512.0, 210.0]],
                    width=3.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].source_id, 'object-left')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-right')


    def test_build_graph_repairs_partial_edge_to_icon_object(self) -> None:
        graph = SceneGraph(
            width=420,
            height=220,
            nodes=[],
            objects=[
                SceneObject(id='object-right', object_type='label_box', bbox=[332, 84, 396, 136], node_ids=[]),
            ],
            icon_objects=[
                IconObject(id='icon-mid', node_id='region-icon-mid', bbox=[168, 76, 252, 148], compound_path='M 0,0 Z', fill='#111111'),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-icon-anchor',
                    node_id='stroke-icon-anchor',
                    points=[[210.0, 148.0], [270.0, 140.0], [332.0, 110.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].source_id, 'icon-mid')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-right')

    def test_build_graph_repairs_long_partial_edge_to_text_cluster(self) -> None:
        graph = SceneGraph(
            width=520,
            height=620,
            nodes=[
                SceneNode(id='text-a', type='text', bbox=[220, 180, 392, 224], z_index=1, vector_mode='text_box', confidence=0.95, text_content='Data Sources'),
                SceneNode(id='text-b', type='text', bbox=[221, 433, 397, 470], z_index=2, vector_mode='text_box', confidence=0.95, text_content='Mutation Data'),
                SceneNode(id='text-c', type='text', bbox=[229, 473, 386, 517], z_index=3, vector_mode='text_box', confidence=0.95, text_content='Clinical Data'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[24, 280, 88, 340], node_ids=[]),
                SceneObject(
                    id='object-text-cluster',
                    object_type='text_cluster',
                    bbox=[220, 180, 397, 517],
                    node_ids=['text-a', 'text-b', 'text-c'],
                ),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-text-cluster',
                    node_id='stroke-text-cluster',
                    points=[[88.0, 320.0], [150.0, 320.0], [232.0, 320.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].source_id, 'object-left')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-text-cluster')

    def test_build_graph_drops_edge_between_overlapping_semantic_objects(self) -> None:
        graph = SceneGraph(
            width=420,
            height=620,
            nodes=[],
            objects=[
                SceneObject(id='object-title', object_type='title', bbox=[125, 182, 292, 224], node_ids=['text-a']),
                SceneObject(id='object-cluster', object_type='text_cluster', bbox=[109, 182, 308, 682], node_ids=['text-a', 'text-b', 'text-c']),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-overlap-drop',
                    node_id='stroke-overlap-drop',
                    points=[[292.0, 210.0], [300.0, 260.0], [308.0, 320.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])

    def test_dedupe_graph_edges_prefers_non_degraded_edge_with_same_backbone(self) -> None:
        deduped = _dedupe_graph_edges([
            GraphEdge(
                id='edge-degraded',
                source_id='object-cluster',
                target_id='text-target',
                source_kind='text_cluster',
                target_kind='text',
                path=[[109.0, 342.0], [798.6, 150.0]],
                backbone_id='stroke-dup',
                metadata={'route_degraded': True},
            ),
            GraphEdge(
                id='edge-good',
                source_id='object-cluster',
                target_id='text-target',
                source_kind='text_cluster',
                target_kind='text',
                path=[[109.0, 342.0], [120.0, 342.0], [120.0, 344.0], [576.0, 344.0], [576.0, 88.0], [824.0, 88.0], [824.0, 160.0], [798.6, 160.0], [798.6, 150.0]],
                backbone_id='stroke-dup',
                metadata={'route_degraded': False},
            ),
        ])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].id, 'edge-good')

    def test_build_graph_dedupes_near_duplicate_edges_across_backbones(self) -> None:
        graph = SceneGraph(
            width=420,
            height=240,
            nodes=[],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[24, 84, 88, 140], node_ids=['region-left']),
                SceneObject(id='object-right', object_type='label_box', bbox=[332, 84, 396, 140], node_ids=['region-right']),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-near-dup-a',
                    node_id='stroke-near-dup-a',
                    points=[[88.0, 110.0], [210.0, 110.0], [332.0, 110.0]],
                    width=2.0,
                    metadata={'semantic_connector': True},
                ),
                StrokePrimitive(
                    id='stroke-primitive-near-dup-b',
                    node_id='stroke-near-dup-b',
                    points=[[88.0, 112.0], [210.0, 112.0], [332.0, 112.0]],
                    width=2.0,
                    metadata={'semantic_connector': True},
                ),
            ],
        )

        updated = build_graph(graph)

        kept = [edge for edge in updated.graph_edges if edge.source_id == 'object-left' and edge.target_id == 'object-right']
        self.assertEqual(len(kept), 1)

    def test_build_graph_drops_degraded_direct_text_cluster_link_without_arrow(self) -> None:
        graph = SceneGraph(
            width=420,
            height=980,
            nodes=[],
            objects=[
                SceneObject(
                    id='object-top-cluster',
                    object_type='text_cluster',
                    bbox=[109, 182, 308, 682],
                    node_ids=['text-a', 'text-b', 'text-c'],
                ),
                SceneObject(
                    id='object-bottom-cluster',
                    object_type='text_cluster',
                    bbox=[53, 689, 365, 880],
                    node_ids=['text-d', 'text-e', 'text-f'],
                ),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-cluster-fragment',
                    node_id='stroke-cluster-fragment',
                    points=[[308.0, 289.0], [228.0, 689.0]],
                    width=2.0,
                    metadata={'semantic_connector': True},
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])

    def test_populate_router_obstacles_skips_excluded_object_member_text_nodes(self) -> None:
        router = FlowchartRouter(240, 240, grid_size=8)
        graph = SceneGraph(
            width=240,
            height=240,
            nodes=[
                SceneNode(id='text-a', type='text', bbox=[80, 80, 160, 120], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Label'),
            ],
            objects=[
                SceneObject(id='object-cluster', object_type='text_cluster', bbox=[60, 60, 180, 140], node_ids=['text-a']),
            ],
        )

        _populate_router_obstacles(
            router,
            graph,
            exclude_ids={'object-cluster'},
            exclude_node_ids={'text-a'},
        )

        self.assertEqual(router.obstacles, set())

    def test_build_graph_drops_short_unanchored_fragment(self) -> None:
        graph = SceneGraph(
            width=320,
            height=220,
            nodes=[],
            objects=[
                SceneObject(id='object-box', object_type='label_box', bbox=[40, 40, 120, 100], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-short-floating',
                    node_id='stroke-short-floating',
                    points=[[180.0, 150.0], [205.0, 168.0], [232.0, 192.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])

    def test_build_graph_drops_loopback_partial_fragment_near_same_anchor(self) -> None:
        graph = SceneGraph(
            width=320,
            height=240,
            nodes=[],
            objects=[
                SceneObject(id='object-box', object_type='label_box', bbox=[120, 182, 292, 224], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-loopback',
                    node_id='stroke-loopback',
                    points=[[223.0, 224.0], [269.0, 289.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])


    def test_build_graph_drops_one_sided_text_edge_when_free_endpoint_is_far_from_any_anchor(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[
                SceneNode(id='text-target', type='text', bbox=[640, 98, 1139, 150], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Large Label'),
                SceneNode(id='text-other', type='text', bbox=[121, 433, 297, 470], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Other Label'),
            ],
            objects=[
                SceneObject(id='object-title', object_type='title', bbox=[125, 182, 292, 224], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-one-sided-far',
                    node_id='stroke-one-sided-far',
                    points=[[163.0, 342.0], [645.0, 150.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])

    def test_build_graph_drops_short_partial_edge_fragment(self) -> None:
        graph = SceneGraph(
            width=300,
            height=160,
            nodes=[],
            objects=[
                SceneObject(id='object-box', object_type='label_box', bbox=[180, 60, 260, 120], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-short-fragment',
                    node_id='stroke-short-fragment',
                    points=[[160.0, 80.0], [170.0, 82.0], [178.0, 81.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])
        self.assertEqual(updated.relations, [])

    def test_build_graph_snaps_to_large_box_boundary_when_endpoint_stops_just_outside(self) -> None:
        graph = SceneGraph(
            width=720,
            height=200,
            nodes=[],
            objects=[
                SceneObject(id='object-left-box', object_type='label_box', bbox=[20, 30, 220, 130], node_ids=[]),
                SceneObject(id='object-right-box', object_type='network_container', bbox=[420, 30, 640, 150], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-gap-snap',
                    node_id='stroke-gap-snap',
                    points=[[30.0, 140.0], [180.0, 140.0], [410.0, 140.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges[0].source_id, 'object-left-box')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-right-box')
        self.assertLessEqual(updated.graph_edges[0].path[0][1], 130.0)
        self.assertGreaterEqual(updated.graph_edges[0].path[-1][0], 420.0)

    def test_build_graph_ray_extension_snaps_to_text_node(self) -> None:
        graph = SceneGraph(
            width=320,
            height=180,
            nodes=[
                SceneNode(
                    id='text-target',
                    type='text',
                    bbox=[210, 62, 282, 98],
                    z_index=1,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Outcome',
                )
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-ray-text',
                    node_id='stroke-ray-text',
                    points=[[120.0, 80.0], [170.0, 80.0], [202.0, 80.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges[0].target_id, 'text-target')
        self.assertGreaterEqual(updated.graph_edges[0].path[-1][0], 210.0)


    def test_build_graph_reroutes_border_hugging_route_inward(self) -> None:
        graph = SceneGraph(
            width=1440,
            height=760,
            nodes=[],
            objects=[
                SceneObject(id='object-region-003', object_type='label_box', bbox=[40, 700, 120, 748], node_ids=[]),
                SceneObject(id='object-region-002', object_type='label_box', bbox=[355, 640, 430, 688], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-border-hug',
                    node_id='stroke-border-hug',
                    points=[[78.6, 741.0], [68.5, 755.0], [105.0, 755.0], [141.5, 755.0], [177.5, 755.0], [214.0, 755.0], [250.5, 755.0], [381.0, 658.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        edge = updated.graph_edges[0]
        self.assertEqual(edge.source_id, 'object-region-003')
        self.assertEqual(edge.target_id, 'object-region-002')
        self.assertGreater(len(edge.path), 2)
        self.assertLess(max(point[1] for point in edge.path[1:-1]), 744.0)
        for left, right in zip(edge.path, edge.path[1:]):
            self.assertTrue(left[0] == right[0] or left[1] == right[1])
        self.assertFalse(edge.metadata.get('route_degraded', False))

    def test_build_graph_drops_monster_strokes_before_edge_construction(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[40, 120, 180, 220], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[720, 120, 860, 220], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-monster-width',
                    node_id='stroke-monster-width',
                    points=[[180.0, 180.0], [620.0, 180.0], [1020.0, 180.0]],
                    width=18.0,
                ),
                StrokePrimitive(
                    id='stroke-primitive-monster-area',
                    node_id='stroke-monster-area',
                    points=[[30.0, 60.0], [1120.0, 60.0], [1120.0, 520.0], [30.0, 520.0]],
                    width=8.0,
                ),
                StrokePrimitive(
                    id='stroke-primitive-valid',
                    node_id='stroke-valid',
                    points=[[176.0, 170.0], [420.0, 170.0], [720.0, 170.0]],
                    width=4.0,
                ),
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].backbone_id, 'stroke-valid')
        self.assertEqual(updated.graph_edges[0].source_id, 'object-left')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-right')

    def test_build_graph_routes_orthogonally_around_text_and_template_obstacles(self) -> None:
        graph = SceneGraph(
            width=420,
            height=240,
            nodes=[
                SceneNode(id='panel-region-000', type='region', bbox=[0, 0, 420, 240], z_index=0, vector_mode='region_path', confidence=0.9, fill='#eef6ff', shape_hint='panel'),
                SceneNode(id='text-obstacle', type='text', bbox=[160, 84, 250, 118], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Central Label'),
                SceneNode(id='template-obstacle', type='region', bbox=[156, 128, 254, 192], z_index=1, vector_mode='region_path', confidence=0.9, fill='#d9e6f2', shape_hint='svg_template'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[24, 84, 88, 140], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[332, 84, 396, 140], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-astar-route',
                    node_id='stroke-astar-route',
                    points=[[88.0, 112.0], [210.0, 112.0], [332.0, 112.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(len(updated.graph_edges), 1)
        edge = updated.graph_edges[0]
        self.assertEqual(edge.source_id, 'object-left')
        self.assertEqual(edge.target_id, 'object-right')
        self.assertGreater(len(edge.path), 2)
        for left, right in zip(edge.path, edge.path[1:]):
            self.assertTrue(left[0] == right[0] or left[1] == right[1])

        padded_obstacles = ([140.0, 64.0, 270.0, 138.0], [144.0, 116.0, 266.0, 204.0])
        for left, right in zip(edge.path, edge.path[1:]):
            for bbox in padded_obstacles:
                self.assertFalse(_segment_intersects_bbox(left, right, bbox))


    def test_build_graph_keeps_nonsemantic_stroke_polyline_shape(self) -> None:
        graph = SceneGraph(
            width=240,
            height=140,
            nodes=[
                SceneNode(id='stroke-decor', type='stroke', bbox=[24, 30, 216, 102], z_index=1, vector_mode='stroke_path', confidence=0.9),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[20, 28, 70, 88], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[170, 60, 220, 120], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-decor',
                    node_id='stroke-decor',
                    points=[[70.0, 40.0], [118.0, 58.0], [170.0, 88.0]],
                    width=2.0,
                    metadata={'semantic_connector': False},
                )
            ],
        )

        updated = build_graph(graph)

        edge = updated.graph_edges[0]
        self.assertEqual(len(edge.path), 3)
        self.assertTrue(any(left[0] != right[0] and left[1] != right[1] for left, right in zip(edge.path, edge.path[1:])))

    def test_build_graph_routes_semantic_connector_around_icon_obstacle(self) -> None:
        graph = SceneGraph(
            width=420,
            height=220,
            nodes=[
                SceneNode(id='stroke-connector', type='stroke', bbox=[84, 90, 336, 130], z_index=1, vector_mode='stroke_path', confidence=0.9, component_role='connector_path'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[24, 84, 88, 136], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[332, 84, 396, 136], node_ids=[]),
            ],
            icon_objects=[
                IconObject(id='icon-mid', node_id='region-icon-mid', bbox=[168, 76, 252, 148], compound_path='M 0,0 Z', fill='#111111'),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-icon-route',
                    node_id='stroke-connector',
                    points=[[88.0, 110.0], [210.0, 110.0], [332.0, 110.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        edge = updated.graph_edges[0]
        self.assertGreater(len(edge.path), 2)
        for left, right in zip(edge.path, edge.path[1:]):
            self.assertTrue(left[0] == right[0] or left[1] == right[1])
            self.assertFalse(_segment_intersects_bbox(left, right, (156.0, 64.0, 264.0, 160.0)))

    def test_build_graph_drops_wide_stroke_covering_ten_percent_of_canvas(self) -> None:
        graph = SceneGraph(
            width=1000,
            height=800,
            nodes=[],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[40, 120, 180, 220], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[720, 120, 860, 220], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-wide-cover',
                    node_id='stroke-wide-cover',
                    points=[[40.0, 40.0], [960.0, 40.0], [960.0, 160.0], [40.0, 160.0]],
                    width=16.0,
                )
            ],
        )

        updated = build_graph(graph)

        self.assertEqual(updated.graph_edges, [])
        self.assertEqual(updated.relations, [])

    def test_build_graph_respects_custom_monster_stroke_thresholds(self) -> None:
        graph = SceneGraph(
            width=1200,
            height=800,
            nodes=[],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[40, 120, 180, 220], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[720, 120, 860, 220], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-custom-threshold',
                    node_id='stroke-custom-threshold',
                    points=[[176.0, 170.0], [420.0, 170.0], [720.0, 170.0]],
                    width=16.0,
                )
            ],
        )
        cfg = PipelineConfig(
            input_path='picture/F2.png',
            output_dir='outputs/F2',
            thresholds=ThresholdConfig(
                graph_monster_stroke_width=20.0,
                graph_monster_stroke_wide_area_ratio=0.20,
                graph_monster_stroke_area_ratio=0.20,
                graph_monster_stroke_diagonal_ratio=0.95,
                graph_monster_stroke_diagonal_width=20.0,
            ),
        )

        updated = build_graph(graph, cfg=cfg)

        self.assertEqual(len(updated.graph_edges), 1)
        self.assertEqual(updated.graph_edges[0].source_id, 'object-left')
        self.assertEqual(updated.graph_edges[0].target_id, 'object-right')

    def test_build_graph_smooths_astar_route_to_key_turn_points(self) -> None:
        graph = SceneGraph(
            width=420,
            height=240,
            nodes=[
                SceneNode(id='text-obstacle', type='text', bbox=[160, 84, 250, 118], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Central Label'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[24, 84, 88, 140], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[332, 84, 396, 140], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-astar-smooth',
                    node_id='stroke-astar-smooth',
                    points=[[88.0, 112.0], [210.0, 112.0], [332.0, 112.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        edge = updated.graph_edges[0]
        self.assertGreater(len(edge.path), 2)
        for first, second, third in zip(edge.path, edge.path[1:], edge.path[2:]):
            self.assertFalse(_are_collinear(first, second, third))

    def test_build_graph_forces_manhattan_path_when_astar_route_is_blocked(self) -> None:
        graph = SceneGraph(
            width=360,
            height=220,
            nodes=[
                SceneNode(id='text-wall', type='text', bbox=[120, 0, 240, 220], z_index=1, vector_mode='text_box', confidence=0.9, text_content='wall'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[20, 84, 72, 136], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[288, 84, 340, 136], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-astar-blocked',
                    node_id='stroke-astar-blocked',
                    points=[[72.0, 110.0], [180.0, 110.0], [288.0, 110.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        edge = updated.graph_edges[0]
        self.assertEqual(edge.source_id, 'object-left')
        self.assertEqual(edge.target_id, 'object-right')
        self.assertGreaterEqual(len(edge.path), 2)
        for left, right in zip(edge.path, edge.path[1:]):
            self.assertTrue(left[0] == right[0] or left[1] == right[1])
        self.assertFalse(edge.metadata.get('route_degraded', False))


    def test_build_graph_retries_routing_with_relaxed_obstacle_padding(self) -> None:
        graph = SceneGraph(
            width=360,
            height=220,
            nodes=[
                SceneNode(id='text-central', type='text', bbox=[120, 20, 240, 200], z_index=1, vector_mode='text_box', confidence=0.9, text_content='central'),
            ],
            objects=[
                SceneObject(id='object-left', object_type='label_box', bbox=[20, 84, 72, 136], node_ids=[]),
                SceneObject(id='object-right', object_type='label_box', bbox=[288, 84, 340, 136], node_ids=[]),
            ],
            stroke_primitives=[
                StrokePrimitive(
                    id='stroke-primitive-astar-relaxed',
                    node_id='stroke-astar-relaxed',
                    points=[[72.0, 110.0], [180.0, 110.0], [288.0, 110.0]],
                    width=2.0,
                )
            ],
        )

        updated = build_graph(graph)

        edge = updated.graph_edges[0]
        self.assertEqual(edge.source_id, 'object-left')
        self.assertEqual(edge.target_id, 'object-right')
        self.assertGreater(len(edge.path), 2)
        self.assertFalse(edge.metadata.get('route_degraded', False))
        self.assertTrue(any(point[1] < 20.0 or point[1] > 200.0 for point in edge.path[1:-1]))


def _segment_intersects_bbox(start: list[float], end: list[float], bbox: tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bbox
    if start[0] == end[0]:
        x = start[0]
        if x < min_x or x > max_x:
            return False
        seg_min_y = min(start[1], end[1])
        seg_max_y = max(start[1], end[1])
        return not (seg_max_y < min_y or seg_min_y > max_y)
    if start[1] == end[1]:
        y = start[1]
        if y < min_y or y > max_y:
            return False
        seg_min_x = min(start[0], end[0])
        seg_max_x = max(start[0], end[0])
        return not (seg_max_x < min_x or seg_min_x > max_x)
    raise AssertionError('expected orthogonal segment')


def _are_collinear(first: list[float], second: list[float], third: list[float]) -> bool:
    return (first[0] == second[0] == third[0]) or (first[1] == second[1] == third[1])


if __name__ == "__main__":
    unittest.main()
