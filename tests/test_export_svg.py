from pathlib import Path
import unittest

from plot2svg.export_svg import build_svg_group_id, export_svg
from plot2svg.object_svg_exporter import _should_prune_raster_object, export_object_scene_graph
from plot2svg.scene_graph import GraphEdge, IconObject, NodeObject, RasterObject, RegionObject, SceneGraph, SceneGroup, SceneNode, SceneObject
from plot2svg.vectorize_region import RegionVectorResult
from plot2svg.vectorize_stroke import StrokeVectorResult


class ExportSvgTest(unittest.TestCase):
    def test_svg_group_ids_are_stable(self) -> None:
        self.assertEqual(build_svg_group_id('component-1'), 'component-1')

    def test_export_svg_writes_final_svg(self) -> None:
        output_dir = Path('outputs/test-export')
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 100, 80], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-1', type='region', bbox=[0, 0, 10, 10], z_index=1, vector_mode='region_path', confidence=0.9, group_id='component-region-1', component_role='container_shape'),
                SceneNode(id='stroke-1', type='stroke', bbox=[0, 0, 10, 10], z_index=2, vector_mode='stroke_path', confidence=0.9),
                SceneNode(id='text-1', type='text', bbox=[10, 10, 60, 30], z_index=3, vector_mode='text_box', confidence=0.9, text_content='LABEL', group_id='component-region-1', component_role='label_text'),
            ],
            groups=[
                SceneGroup(
                    id='component-region-1',
                    role='labeled_region',
                    bbox=[0, 0, 60, 30],
                    child_ids=['region-1', 'text-1'],
                )
            ],
            objects=[
                SceneObject(
                    id='object-region-1',
                    object_type='label_box',
                    bbox=[0, 0, 60, 30],
                    node_ids=['region-1', 'text-1'],
                    group_ids=['component-region-1'],
                )
            ],
        )
        export_result = export_svg(
            graph,
            [RegionVectorResult(component_id='region-1', svg_fragment="<path id='region-1' />", path_count=1, simplified=False)],
            [StrokeVectorResult(component_id='stroke-1', svg_fragment='M 0 0 C 1 1 2 2 3 3', curve_count=1)],
            output_dir,
        )
        self.assertTrue(export_result.svg_path.exists())
        self.assertTrue(export_result.preview_path.exists())
        self.assertGreater(export_result.preview_path.stat().st_size, 0)
        self.assertEqual(export_result.group_count, 2)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')
        self.assertIn('<text', svg_content)
        self.assertIn("data-component-role='labeled_region'", svg_content)
        self.assertIn("data-object-type='label_box'", svg_content)

    def test_export_svg_renders_multiline_text_with_tspans(self) -> None:
        output_dir = Path('outputs/test-export-multiline-text')
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(
                    id='text-multi',
                    type='text',
                    bbox=[20, 20, 140, 80],
                    z_index=1,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='HELLO\nWORLD',
                    stroke='#000000',
                ),
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn('<tspan', svg_content)
        self.assertIn('HELLO', svg_content)
        self.assertIn('WORLD', svg_content)

    def test_export_svg_injects_standard_arrow_marker_defs(self) -> None:
        output_dir = Path('outputs/test-export-arrow-marker-defs')
        graph = SceneGraph(
            width=120,
            height=80,
            nodes=[],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-arrow-defs',
                    source_id='node-a',
                    target_id='node-b',
                    path=[[20.0, 40.0], [100.0, 40.0]],
                    arrow_head={'tip': [100.0, 40.0], 'left': [90.0, 36.0], 'right': [90.0, 44.0]},
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("<defs>", svg_content)
        self.assertIn("id='standard-arrow'", svg_content)
        self.assertIn("marker-end='url(#standard-arrow)'", svg_content)

    def test_export_svg_renders_icon_object_with_evenodd_before_edges_and_text(self) -> None:
        output_dir = Path('outputs/test-export-icon-object')
        graph = SceneGraph(
            width=160,
            height=120,
            nodes=[
                SceneNode(id='text-1', type='text', bbox=[80, 80, 130, 100], z_index=4, vector_mode='text_box', confidence=0.9, text_content='LABEL'),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-1',
                    node_id='region-1',
                    outer_path='M 10 10 L 70 10 L 70 60 L 10 60 Z',
                    holes=[],
                    fill='#dddddd',
                    stroke='#999999',
                )
            ],
            icon_objects=[
                IconObject(
                    id='icon-object-1',
                    node_id='region-icon-1',
                    bbox=[72, 18, 100, 46],
                    compound_path='M 72,18 L 100,18 L 100,46 L 72,46 Z M 78,24 L 94,24 L 94,40 L 78,40 Z',
                    fill='#111111',
                    fill_rule='evenodd',
                )
            ],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-1',
                    source_id='node-1',
                    target_id='node-2',
                    path=[[70.0, 35.0], [100.0, 35.0]],
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("class='icon-object'", svg_content)
        self.assertIn("fill-rule='evenodd'", svg_content)
        self.assertLess(svg_content.index("class='region'"), svg_content.index("class='icon-object'"))
        self.assertLess(svg_content.index("class='icon-object'"), svg_content.index("class='edge'"))
        self.assertLess(svg_content.index("class='edge'"), svg_content.index('<text'))

    def test_export_svg_prefers_object_driven_render_order(self) -> None:
        output_dir = Path('outputs/test-export-object-driven')
        graph = SceneGraph(
            width=160,
            height=120,
            nodes=[
                SceneNode(id='text-1', type='text', bbox=[80, 80, 130, 100], z_index=4, vector_mode='text_box', confidence=0.9, text_content='LABEL'),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-1',
                    node_id='region-1',
                    outer_path='M 10 10 L 70 10 L 70 60 L 10 60 Z',
                    holes=[],
                    fill='#dddddd',
                    stroke='#999999',
                )
            ],
            raster_objects=[
                RasterObject(
                    id='raster-object-1',
                    node_id='region-icon-1',
                    bbox=[72, 18, 100, 46],
                    image_href='data:image/png;base64,AAAA',
                )
            ],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-1',
                    source_id='node-1',
                    target_id='node-2',
                    path=[[70.0, 35.0], [100.0, 35.0]],
                )
            ],
            node_objects=[
                NodeObject(id='node-1', node_id='circle-1', center=[60.0, 35.0], radius=8.0, fill='#336699'),
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertLess(svg_content.index("class='region'"), svg_content.index("class='raster-object'"))
        self.assertLess(svg_content.index("class='raster-object'"), svg_content.index("class='node'"))
        self.assertLess(svg_content.index("class='node'"), svg_content.index("class='edge'"))
        self.assertLess(svg_content.index("class='edge'"), svg_content.index('<text'))

    def test_export_svg_renders_polygon_node_objects_without_circle_fallback(self) -> None:
        output_dir = Path('outputs/test-export-polygon-nodes')
        graph = SceneGraph(
            width=200,
            height=160,
            nodes=[],
            node_objects=[
                NodeObject(
                    id='node-triangle',
                    node_id='triangle-1',
                    center=[60.0, 60.0],
                    radius=18.0,
                    fill='#ff8800',
                    metadata={
                        'shape_type': 'triangle',
                        'vertex_count': 3,
                        'orientation': {'direction': 'up', 'angle_degrees': -90.0},
                    },
                ),
                NodeObject(
                    id='node-pentagon',
                    node_id='pentagon-1',
                    center=[130.0, 80.0],
                    radius=20.0,
                    fill='#0088ff',
                    metadata={
                        'shape_type': 'pentagon',
                        'vertex_count': 5,
                    },
                ),
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("<polygon id='node-triangle' class='node'", svg_content)
        self.assertIn("<polygon id='node-pentagon' class='node'", svg_content)
        self.assertNotIn("<circle id='node-triangle'", svg_content)
        self.assertNotIn("<circle id='node-pentagon'", svg_content)


    def test_export_svg_renders_panel_rectangle_with_rounded_corners(self) -> None:
        output_dir = Path('outputs/test-export-panel-rounded')
        graph = SceneGraph(
            width=240,
            height=160,
            nodes=[
                SceneNode(id='panel-node', type='region', bbox=[20, 30, 180, 110], z_index=1, vector_mode='region_path', confidence=0.9, fill='#eef6ff', shape_hint='panel'),
            ],
            region_objects=[
                RegionObject(
                    id='region-panel-1',
                    node_id='panel-node',
                    outer_path='M 20 30 L 180 30 L 180 110 L 20 110 Z',
                    holes=[],
                    fill='#eef6ff',
                    stroke='#7a8ea8',
                    metadata={'shape_type': 'rectangle', 'rectangle': {'x': 20.0, 'y': 30.0, 'width': 160.0, 'height': 80.0}},
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("data-shape-type='rectangle'", svg_content)
        self.assertIn("rx='", svg_content)
        self.assertIn("ry='", svg_content)

    def test_should_prune_small_raster_candidate_before_svg_export(self) -> None:
        raster_obj = RasterObject(
            id='raster-noise-1',
            node_id='region-noise-1',
            bbox=[10, 15, 34, 39],
            image_href='data:image/png;base64,AAAA',
            metadata={'shape_hint': 'raster_candidate', 'variance': 1800.0},
        )

        self.assertTrue(_should_prune_raster_object(raster_obj))

    def test_export_svg_renders_raster_object_as_image(self) -> None:
        output_dir = Path('outputs/test-export-raster-object')
        graph = SceneGraph(
            width=120,
            height=90,
            nodes=[],
            raster_objects=[
                RasterObject(
                    id='raster-icon-1',
                    node_id='region-icon-1',
                    bbox=[10, 15, 50, 55],
                    image_href='data:image/png;base64,AAAA',
                    metadata={'source': 'pipeline'},
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn('<image', svg_content)
        self.assertIn("xmlns:xlink='http://www.w3.org/1999/xlink'", svg_content)
        self.assertIn("id='raster-icon-1'", svg_content)
        self.assertIn("href='data:image/png;base64,AAAA'", svg_content)
        self.assertIn("xlink:href='data:image/png;base64,AAAA'", svg_content)

    def test_export_svg_replaces_raster_candidate_with_context_template(self) -> None:
        output_dir = Path('outputs/test-export-raster-template-context')
        graph = SceneGraph(
            width=220,
            height=180,
            nodes=[
                SceneNode(
                    id='region-icon-1',
                    type='region',
                    bbox=[20, 20, 90, 90],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.8,
                    fill='#dbe8f5',
                ),
                SceneNode(
                    id='text-data',
                    type='text',
                    bbox=[18, 96, 130, 118],
                    z_index=2,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Data Sources',
                ),
            ],
            raster_objects=[
                RasterObject(
                    id='raster-icon-1',
                    node_id='region-icon-1',
                    bbox=[20, 20, 90, 90],
                    image_href='data:image/png;base64,AAAA',
                    metadata={'shape_hint': 'raster_candidate', 'variance': 2400.0},
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("class='svg-template raster-template'", svg_content)
        self.assertIn("data-template-name='database'", svg_content)
        self.assertNotIn("class='raster-object'", svg_content)
        self.assertNotIn('<image', svg_content)




    def test_export_object_scene_graph_drops_small_region_inside_emitted_template_bbox(self) -> None:
        graph = SceneGraph(
            width=400,
            height=260,
            nodes=[
                SceneNode(id='region-small-1', type='region', bbox=[205, 130, 218, 143], z_index=0, vector_mode='region_path', confidence=0.9, fill='#aa8844'),
                SceneNode(id='container-detail-region-a', type='region', bbox=[200, 70, 240, 95], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-023'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[300, 120, 332, 220], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-023'),
                SceneNode(id='text-overlay-023', type='text', bbox=[210, 96, 330, 118], z_index=3, vector_mode='text_box', confidence=0.9, text_content='feature engineering', group_id='component-text-overlay-023'),
            ],
            region_objects=[
                RegionObject(id='region-object-small-1', node_id='region-small-1', outer_path='M 205 130 L 218 130 L 218 143 L 205 143 Z', holes=[], fill='#aa8844', stroke='#aa8844'),
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 200 70 L 240 70 L 240 95 L 200 95 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 300 120 L 332 120 L 332 220 L 300 220 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='feature_panel'", svg)
        self.assertNotIn("id='region-object-small-1' class='region'", svg)

    def test_export_object_scene_graph_drops_centered_small_region_inside_template_bbox(self) -> None:
        graph = SceneGraph(
            width=420,
            height=280,
            nodes=[
                SceneNode(id='region-small-2', type='region', bbox=[312, 205, 326, 222], z_index=0, vector_mode='region_path', confidence=0.9, fill='#d94a3a'),
                SceneNode(id='container-detail-region-a', type='region', bbox=[200, 70, 240, 95], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-023'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[300, 120, 332, 220], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-023'),
                SceneNode(id='text-overlay-023', type='text', bbox=[210, 96, 330, 118], z_index=3, vector_mode='text_box', confidence=0.9, text_content='feature engineering', group_id='component-text-overlay-023'),
            ],
            region_objects=[
                RegionObject(id='region-object-small-2', node_id='region-small-2', outer_path='M 312 205 L 326 205 L 326 222 L 312 222 Z', holes=[], fill='#d94a3a', stroke='#d94a3a'),
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 200 70 L 240 70 L 240 95 L 200 95 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 300 120 L 332 120 L 332 220 L 300 220 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='feature_panel'", svg)
        self.assertNotIn("id='region-object-small-2' class='region'", svg)

    def test_export_object_scene_graph_keeps_container_shape_outside_template_groups(self) -> None:
        graph = SceneGraph(
            width=440,
            height=320,
            nodes=[
                SceneNode(id='region-container-shape', type='region', bbox=[40, 180, 150, 290], z_index=0, vector_mode='region_path', confidence=0.9, fill='#f0e0f0', group_id='component-text-overlay-036', component_role='container_shape'),
                SceneNode(id='container-detail-region-a', type='region', bbox=[200, 70, 240, 95], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-023'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[300, 120, 332, 220], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-023'),
                SceneNode(id='text-overlay-023', type='text', bbox=[210, 96, 330, 118], z_index=3, vector_mode='text_box', confidence=0.9, text_content='feature engineering', group_id='component-text-overlay-023'),
                SceneNode(id='text-overlay-036', type='text', bbox=[60, 190, 130, 208], z_index=4, vector_mode='text_box', confidence=0.9, text_content='PrimeKG', group_id='component-text-overlay-036'),
            ],
            region_objects=[
                RegionObject(id='region-object-container-shape', node_id='region-container-shape', outer_path='M 40 180 L 150 180 L 150 290 L 40 290 Z', holes=[], fill='#f0e0f0', stroke='#f0e0f0'),
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 200 70 L 240 70 L 240 95 L 200 95 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 300 120 L 332 120 L 332 220 L 300 220 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='feature_panel'", svg)
        self.assertIn("id='region-object-container-shape' class='region'", svg)

    def test_export_object_scene_graph_drops_tiny_region_adjacent_to_template_bbox(self) -> None:
        graph = SceneGraph(
            width=520,
            height=360,
            nodes=[
                SceneNode(id='region-small-adjacent', type='region', bbox=[248, 170, 262, 186], z_index=0, vector_mode='region_path', confidence=0.9, fill='#d94a3a'),
                SceneNode(id='container-detail-region-a', type='region', bbox=[300, 110, 340, 145], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-012'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[400, 160, 432, 280], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-012', type='text', bbox=[320, 292, 420, 310], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Time (years) Low risk High risk', group_id='component-text-overlay-012'),
            ],
            region_objects=[
                RegionObject(id='region-object-small-adjacent', node_id='region-small-adjacent', outer_path='M 248 170 L 262 170 L 262 186 L 248 186 Z', holes=[], fill='#d94a3a', stroke='#d94a3a'),
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 300 110 L 340 110 L 340 145 L 300 145 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 400 160 L 432 160 L 432 280 L 400 280 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='survival_curve'", svg)
        self.assertNotIn("id='region-object-small-adjacent' class='region'", svg)

    def test_export_object_scene_graph_promotes_feature_panel_template_from_anchor_text(self) -> None:
        graph = SceneGraph(
            width=400,
            height=260,
            nodes=[
                SceneNode(id='region-container', type='region', bbox=[180, 60, 340, 230], z_index=0, vector_mode='region_path', confidence=0.9, fill='#f0e0f0', group_id='component-text-overlay-023', component_role='container_shape'),
                SceneNode(id='container-detail-region-a', type='region', bbox=[200, 70, 240, 95], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-023'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[300, 120, 332, 220], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-023'),
                SceneNode(id='text-overlay-023', type='text', bbox=[210, 96, 330, 118], z_index=3, vector_mode='text_box', confidence=0.9, text_content='feature engineering', group_id='component-text-overlay-023'),
            ],
            region_objects=[
                RegionObject(id='region-object-container', node_id='region-container', outer_path='M 180 60 L 340 60 L 340 230 L 180 230 Z', holes=[], fill='#f0e0f0', stroke='#f0e0f0'),
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 200 70 L 240 70 L 240 95 L 200 95 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 300 120 L 332 120 L 332 220 L 300 220 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='feature_panel'", svg)
        self.assertEqual(svg.count("data-template-name='feature_panel'"), 1)
        self.assertNotIn("id='region-object-container' class='region'", svg)

    def test_export_object_scene_graph_collapses_detail_regions_into_semantic_group_template(self) -> None:
        graph = SceneGraph(
            width=260,
            height=180,
            nodes=[
                SceneNode(id='container-detail-region-1', type='region', bbox=[40, 30, 80, 70], z_index=1, vector_mode='region_path', confidence=0.9, fill='#5b8def', group_id='component-text-overlay-016'),
                SceneNode(id='container-detail-region-2', type='region', bbox=[90, 40, 130, 78], z_index=2, vector_mode='region_path', confidence=0.9, fill='#c06c84', group_id='component-text-overlay-016'),
                SceneNode(id='container-detail-region-3', type='region', bbox=[70, 82, 112, 120], z_index=3, vector_mode='region_path', confidence=0.9, fill='#7abf6a', group_id='component-text-overlay-016'),
                SceneNode(id='text-gene', type='text', bbox=[20, 126, 70, 144], z_index=4, vector_mode='text_box', confidence=0.9, text_content='Gene Disease Pathway node embedding module'),
            ],
            region_objects=[
                RegionObject(id='region-object-1', node_id='container-detail-region-1', outer_path='M 40 30 L 80 30 L 80 70 L 40 70 Z', holes=[], fill='#5b8def', stroke='#5b8def'),
                RegionObject(id='region-object-2', node_id='container-detail-region-2', outer_path='M 90 40 L 130 40 L 130 78 L 90 78 Z', holes=[], fill='#c06c84', stroke='#c06c84'),
                RegionObject(id='region-object-3', node_id='container-detail-region-3', outer_path='M 70 82 L 112 82 L 112 120 L 70 120 Z', holes=[], fill='#7abf6a', stroke='#7abf6a'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("data-template-name='hetero_graph'", svg)
        self.assertEqual(svg.count("data-template-name='hetero_graph'"), 1)
        self.assertNotIn("id='region-object-1' class='region'", svg)
        self.assertNotIn("id='region-object-2' class='region'", svg)
        self.assertNotIn("id='region-object-3' class='region'", svg)

    def test_export_svg_renders_svg_template_region_object_without_image_fallback(self) -> None:
        output_dir = Path('outputs/test-export-svg-template-region')
        graph = SceneGraph(
            width=220,
            height=180,
            nodes=[],
            region_objects=[
                RegionObject(
                    id='region-object-template',
                    node_id='region-template',
                    outer_path='M 20 20 L 120 20 L 120 120 L 20 120 Z',
                    holes=[],
                    fill='#dbe8f5',
                    stroke='#355070',
                    metadata={
                        'shape_type': 'svg_template',
                        'template_name': 'database',
                        'template_bbox': [20, 20, 120, 120],
                    },
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn("class='svg-template'", svg_content)
        self.assertIn("data-template-name='database'", svg_content)
        self.assertNotIn('<image', svg_content)

    def test_export_svg_renders_rectangle_region_object(self) -> None:
        output_dir = Path('outputs/test-export-rectangle-region')
        graph = SceneGraph(
            width=240,
            height=180,
            nodes=[],
            region_objects=[
                RegionObject(
                    id='region-object-rect',
                    node_id='region-rect',
                    outer_path='M 24 30 L 216 30 L 216 150 L 24 150 Z',
                    holes=[],
                    fill='#c4e0fc',
                    fill_opacity=0.9,
                    stroke='#2f6db2',
                    metadata={
                        'shape_type': 'rectangle',
                        'rectangle': {'x': 24.0, 'y': 30.0, 'width': 192.0, 'height': 120.0},
                    },
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn('<rect', svg_content)
        self.assertIn("data-shape-type='rectangle'", svg_content)

    def test_export_svg_renders_ellipse_region_object(self) -> None:
        output_dir = Path('outputs/test-export-ellipse-region')
        graph = SceneGraph(
            width=220,
            height=180,
            nodes=[],
            region_objects=[
                RegionObject(
                    id='region-object-ellipse',
                    node_id='region-ellipse',
                    outer_path='M 0 0 Z',
                    holes=[],
                    fill='#e2c2d6',
                    fill_opacity=0.8,
                    stroke='#775577',
                    metadata={
                        'shape_type': 'ellipse',
                        'ellipse': {'cx': 110.0, 'cy': 90.0, 'rx': 60.0, 'ry': 42.0, 'rotation': 18.0},
                    },
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn('<ellipse', svg_content)
        self.assertIn("data-shape-type='ellipse'", svg_content)

    def test_export_svg_renders_circle_region_object(self) -> None:
        output_dir = Path('outputs/test-export-circle-region')
        graph = SceneGraph(
            width=220,
            height=180,
            nodes=[],
            region_objects=[
                RegionObject(
                    id='region-object-circle',
                    node_id='region-circle',
                    outer_path='M 0 0 Z',
                    holes=[],
                    fill='#dde8ff',
                    stroke='#556677',
                    metadata={
                        'shape_type': 'circle',
                        'circle': {'cx': 110.0, 'cy': 90.0, 'r': 42.0},
                    },
                )
            ],
        )

        export_result = export_svg(graph, [], [], output_dir)
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertIn('<circle', svg_content)
        self.assertIn("data-shape-type='circle'", svg_content)

    def test_export_object_scene_graph_renders_circle_hint_container_as_ellipse(self) -> None:
        graph = SceneGraph(
            width=260,
            height=220,
            nodes=[
                SceneNode(
                    id='region-circle-container',
                    type='region',
                    bbox=[60, 50, 180, 170],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f0e0f0',
                    group_id='component-text-overlay-036',
                    component_role='container_shape',
                    shape_hint='circle',
                )
            ],
            region_objects=[
                RegionObject(
                    id='region-object-circle-container',
                    node_id='region-circle-container',
                    outer_path='M 60 50 L 180 50 L 180 170 L 60 170 Z',
                    holes=[],
                    fill='#f0e0f0',
                    stroke='#f0e0f0',
                )
            ],
        )

        fragments = export_object_scene_graph(graph)
        svg = "\n".join(fragments)

        self.assertIn("id='region-object-circle-container' class='region'", svg)
        self.assertIn("data-shape-type='ellipse'", svg)
        self.assertNotIn("d='M 60 50 L 180 50 L 180 170 L 60 170 Z'", svg)

    def test_export_svg_skips_invalid_region_objects_without_fallback(self) -> None:
        output_dir = Path('outputs/test-export-invalid-region-skip')
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(id='region-ghost', type='region', bbox=[20, 20, 70, 70], z_index=1, vector_mode='region_path', confidence=0.5),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-ghost',
                    node_id='region-ghost',
                    outer_path='M 20 20 L 70 20 L 70 70 L 20 70 Z',
                    holes=[],
                    fill='#f8f8e8',
                    stroke='#f8f8e8',
                    metadata={'entity_valid': False, 'reject_reason': 'background-like'},
                )
            ],
        )

        export_result = export_svg(
            graph,
            [RegionVectorResult(component_id='region-ghost', svg_fragment="<path id='legacy-ghost' />", path_count=1, simplified=False)],
            [],
            output_dir,
        )
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertNotIn('region-object-ghost', svg_content)
        self.assertNotIn('legacy-ghost', svg_content)


    def test_object_export_skips_text_overlay_container_fallbacks(self) -> None:
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(
                    id='region-text-box',
                    type='region',
                    bbox=[20, 20, 90, 60],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.8,
                    group_id='component-text-overlay-000',
                    component_role='container_shape',
                    shape_hint='raster_candidate',
                ),
                SceneNode(
                    id='region-other-box',
                    type='region',
                    bbox=[100, 20, 150, 60],
                    z_index=2,
                    vector_mode='region_path',
                    confidence=0.8,
                    group_id='component-region-123',
                    component_role='container_shape',
                ),
            ],
        )

        fragments = export_object_scene_graph(
            graph,
            fallback_region_map={
                'region-text-box': RegionVectorResult(component_id='region-text-box', svg_fragment="<path id='legacy-text-box' d='M 20 20 L 90 20 L 90 60 L 20 60 Z' />", path_count=1, simplified=False),
                'region-other-box': RegionVectorResult(component_id='region-other-box', svg_fragment="<path id='legacy-other-box' d='M 100 20 L 150 20 L 150 60 L 100 60 Z' />", path_count=1, simplified=False),
            },
        )

        self.assertFalse(any('legacy-text-box' in fragment for fragment in fragments))
        self.assertTrue(any('legacy-other-box' in fragment for fragment in fragments))


    def test_export_svg_hard_drops_wrapped_black_region_fragment(self) -> None:
        output_dir = Path('outputs/test-export-drop-black-region-group')
        graph = SceneGraph(
            width=100,
            height=80,
            nodes=[
                SceneNode(id='region-black', type='region', bbox=[10, 10, 60, 50], z_index=1, vector_mode='region_path', confidence=0.8),
                SceneNode(id='text-1', type='text', bbox=[12, 54, 70, 72], z_index=2, vector_mode='text_box', confidence=0.9, text_content='Panel'),
            ],
        )

        export_result = export_svg(
            graph,
            [RegionVectorResult(component_id='region-black', svg_fragment="<path id='region-black' d='M 10 10 L 60 10 L 60 50 L 10 50 Z' fill='#000000' stroke='#000000' />", path_count=1, simplified=False)],
            [],
            output_dir,
        )
        svg_content = export_result.svg_path.read_text(encoding='utf-8')

        self.assertNotIn("id='region-black'", svg_content)
        self.assertIn('<text', svg_content)

    def test_object_export_skips_pure_black_region_fallback(self) -> None:
        graph = SceneGraph(
            width=120,
            height=80,
            nodes=[
                SceneNode(id='region-black', type='region', bbox=[10, 10, 50, 50], z_index=1, vector_mode='region_path', confidence=0.7),
            ],
        )

        fragments = export_object_scene_graph(
            graph,
            fallback_region_map={
                'region-black': RegionVectorResult(component_id='region-black', svg_fragment="<path id='legacy-black' d='M 10 10 L 50 10 L 50 50 L 10 50 Z' fill='#000000' stroke='#000000' />", path_count=1, simplified=False),
            },
        )

        self.assertFalse(any('legacy-black' in fragment for fragment in fragments))

    def test_object_export_skips_empty_region_fallback_paths(self) -> None:
        graph = SceneGraph(
            width=120,
            height=80,
            nodes=[
                SceneNode(id='region-empty', type='region', bbox=[10, 10, 40, 40], z_index=1, vector_mode='region_path', confidence=0.7),
                SceneNode(id='region-valid', type='region', bbox=[50, 10, 90, 40], z_index=2, vector_mode='region_path', confidence=0.7),
            ],
        )

        fragments = export_object_scene_graph(
            graph,
            fallback_region_map={
                'region-empty': RegionVectorResult(component_id='region-empty', svg_fragment="<path id='legacy-empty' d='' fill='#000000' stroke='#000000' />", path_count=1, simplified=False),
                'region-valid': RegionVectorResult(component_id='region-valid', svg_fragment="<path id='legacy-valid' d='M 50 10 L 90 10 L 90 40 L 50 40 Z' />", path_count=1, simplified=False),
            },
        )

        self.assertFalse(any('legacy-empty' in fragment for fragment in fragments))
        self.assertTrue(any('legacy-valid' in fragment for fragment in fragments))

    def test_object_export_skips_fallback_region_when_raster_object_exists(self) -> None:
        graph = SceneGraph(
            width=160,
            height=120,
            nodes=[
                SceneNode(id='region-icon-1', type='region', bbox=[20, 20, 70, 70], z_index=1, vector_mode='region_path', confidence=0.8),
            ],
            raster_objects=[
                RasterObject(
                    id='raster-icon-1',
                    node_id='region-icon-1',
                    bbox=[20, 20, 70, 70],
                    image_href='data:image/png;base64,AAAA',
                )
            ],
        )

        fragments = export_object_scene_graph(
            graph,
            fallback_region_map={
                'region-icon-1': RegionVectorResult(component_id='region-icon-1', svg_fragment="<path id='legacy-icon' d='M 20 20 L 70 20 L 70 70 L 20 70 Z' />", path_count=1, simplified=False)
            },
        )

        self.assertTrue(any("class='raster-object'" in fragment for fragment in fragments))
        self.assertFalse(any('legacy-icon' in fragment for fragment in fragments))


    def test_object_export_renders_top_layer_text_with_arial_and_escaped_content(self) -> None:
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(
                    id='text-escaped',
                    type='text',
                    bbox=[30, 20, 140, 42],
                    z_index=5,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='A < B & C',
                ),
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertEqual(len(fragments), 1)
        self.assertIn("font-family='Arial'", fragments[0])
        self.assertIn("y='42'", fragments[0])
        self.assertIn('A &lt; B &amp; C', fragments[0])

    def test_object_export_keeps_text_after_fallback_fragments(self) -> None:
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(id='region-fallback', type='region', bbox=[10, 10, 80, 70], z_index=1, vector_mode='region_path', confidence=0.7),
                SceneNode(id='stroke-fallback', type='stroke', bbox=[20, 30, 140, 40], z_index=2, vector_mode='stroke_path', confidence=0.7),
                SceneNode(id='text-top', type='text', bbox=[30, 80, 120, 102], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Phenotype'),
            ],
        )

        fragments = export_object_scene_graph(
            graph,
            fallback_region_map={
                'region-fallback': RegionVectorResult(component_id='region-fallback', svg_fragment="<path id='legacy-region' d='M 10 10 L 80 10 L 80 70 L 10 70 Z' />", path_count=1, simplified=False)
            },
            fallback_stroke_map={
                'stroke-fallback': StrokeVectorResult(component_id='stroke-fallback', svg_fragment='M 20 35 L 140 35', curve_count=1)
            },
        )

        text_index = next(index for index, fragment in enumerate(fragments) if "class='text'" in fragment)
        region_index = next(index for index, fragment in enumerate(fragments) if 'legacy-region' in fragment)
        stroke_index = next(index for index, fragment in enumerate(fragments) if "id='stroke-fallback'" in fragment)
        self.assertGreater(text_index, region_index)
        self.assertGreater(text_index, stroke_index)

    def test_object_export_filters_white_text_backdrop_rectangles(self) -> None:
        graph = SceneGraph(
            width=180,
            height=120,
            nodes=[
                SceneNode(id='text-1', type='text', bbox=[32, 30, 118, 50], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Pathways'),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-backdrop',
                    node_id='region-backdrop',
                    outer_path='M 20 20 L 130 20 L 130 60 L 20 60 Z',
                    holes=[],
                    fill='#ffffff',
                    fill_opacity=0.98,
                    stroke='#ffffff',
                    metadata={
                        'shape_type': 'rectangle',
                        'is_text_backdrop': True,
                        'contains_text': True,
                    },
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertFalse(any('region-object-backdrop' in fragment for fragment in fragments))

    def test_object_export_skips_large_dark_region_artifact(self) -> None:
        graph = SceneGraph(
            width=200,
            height=100,
            nodes=[
                SceneNode(
                    id='region-dark-artifact',
                    type='region',
                    bbox=[10, 10, 90, 55],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.7,
                )
            ],
            region_objects=[
                RegionObject(
                    id='region-object-dark-artifact',
                    node_id='region-dark-artifact',
                    outer_path='M 10 10 L 90 10 L 90 55 L 10 55 Z',
                    holes=[],
                    fill='#000000',
                    stroke='#000000',
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertFalse(any('region-object-dark-artifact' in fragment for fragment in fragments))

    def test_object_export_renders_graph_edge_as_line_with_marker(self) -> None:
        graph = SceneGraph(
            width=200,
            height=120,
            nodes=[],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-line-arrow',
                    source_id='node-1',
                    target_id='node-2',
                    path=[[20.0, 40.0], [80.0, 40.0]],
                    arrow_head={'tip': [80.0, 40.0], 'left': [70.0, 36.0], 'right': [70.0, 44.0]},
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertTrue(any("<line id='graph-edge-line-arrow'" in fragment for fragment in fragments))
        self.assertTrue(any("marker-end='url(#standard-arrow)'" in fragment for fragment in fragments))
        self.assertFalse(any("class='edge-arrow'" in fragment for fragment in fragments))

    def test_object_export_skips_absurd_arrowhead_polygon(self) -> None:
        graph = SceneGraph(
            width=200,
            height=120,
            nodes=[],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-bad-arrow',
                    source_id='node-1',
                    target_id='node-2',
                    path=[[20.0, 40.0], [80.0, 40.0]],
                    arrow_head={
                        'tip': [80.0, 40.0],
                        'left': [5842.7, -2089.5],
                        'right': [2243.5, -5688.7],
                    },
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertTrue(any("class='edge'" in fragment for fragment in fragments))
        self.assertFalse(any("class='edge-arrow'" in fragment for fragment in fragments))

    def test_object_export_skips_edge_outside_canvas(self) -> None:
        graph = SceneGraph(
            width=200,
            height=120,
            nodes=[],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-offscreen',
                    source_id=None,
                    target_id='object-node',
                    path=[[20.0, 130.0], [80.0, 132.0], [140.0, 131.0]],
                    arrow_head={'tip': [140.0, 131.0], 'left': [132.0, 128.0], 'right': [132.0, 134.0]},
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertFalse(any('graph-edge-offscreen' in fragment for fragment in fragments))

    def test_object_export_skips_edge_without_any_anchor(self) -> None:
        graph = SceneGraph(
            width=200,
            height=120,
            nodes=[],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-unanchored',
                    source_id=None,
                    target_id=None,
                    path=[[20.0, 80.0], [80.0, 82.0], [140.0, 81.0]],
                    arrow_head={'tip': [140.0, 81.0], 'left': [132.0, 78.0], 'right': [132.0, 84.0]},
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertFalse(any('graph-edge-unanchored' in fragment for fragment in fragments))


    def test_object_export_drops_region_overlapping_text_box(self) -> None:
        graph = SceneGraph(
            width=220,
            height=140,
            nodes=[
                SceneNode(
                    id='text-1',
                    type='text',
                    bbox=[40, 40, 140, 80],
                    z_index=2,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Overlay',
                ),
                SceneNode(
                    id='region-1',
                    type='region',
                    bbox=[38, 38, 142, 82],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.8,
                    fill='#111111',
                ),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-1',
                    node_id='region-1',
                    outer_path='M 38 38 L 142 38 L 142 82 L 38 82 Z',
                    holes=[],
                    fill='#111111',
                    stroke='#111111',
                )
            ],
        )

        fragments = export_object_scene_graph(graph)

        self.assertFalse(any("id='region-object-1'" in fragment for fragment in fragments))
        self.assertTrue(any("id='text-1'" in fragment for fragment in fragments))

    def test_object_export_renders_panel_arrow_as_filled_path(self) -> None:
        graph = SceneGraph(
            width=240,
            height=140,
            nodes=[
                SceneNode(
                    id='panel-arrow-node',
                    type='region',
                    bbox=[30, 40, 130, 80],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.95,
                    fill='#703080',
                    stroke='#703080',
                    shape_hint='panel_arrow',
                )
            ],
            region_objects=[
                RegionObject(
                    id='region-object-panel-arrow',
                    node_id='panel-arrow-node',
                    outer_path='M 30 40 L 100 40 L 130 60 L 100 80 L 30 80 Z',
                    holes=[],
                    fill='#703080',
                    stroke='#703080',
                    fill_opacity=0.98,
                    metadata={'shape_type': 'panel_arrow_template', 'template_bbox': [30, 40, 130, 80], 'orientation': 'right'},
                )
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\n'.join(fragments)

        self.assertIn("class='region panel-arrow'", joined)
        self.assertIn("fill='#703080'", joined)
        self.assertIn("d='M 30 40 L 100 40 L 130 60 L 100 80 L 30 80 Z'", joined)
        self.assertNotIn('marker-end=', joined)
        self.assertNotIn('<line', joined)

    def test_object_export_force_snaps_edge_endpoint_to_nearby_text_anchor(self) -> None:
        graph = SceneGraph(
            width=260,
            height=140,
            nodes=[
                SceneNode(
                    id='text-target',
                    type='text',
                    bbox=[180, 40, 240, 76],
                    z_index=1,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Target',
                )
            ],
            graph_edges=[
                GraphEdge(
                    id='graph-edge-near-text',
                    source_id='node-a',
                    target_id=None,
                    path=[[30.0, 58.0], [90.0, 58.0], [150.0, 58.0]],
                    arrow_head={'tip': [150.0, 58.0], 'left': [142.0, 54.0], 'right': [142.0, 62.0]},
                )
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\\n'.join(fragments)

        self.assertIn("data-target-id='text-target'", joined)
        self.assertIn("marker-end='url(#standard-arrow)'", joined)
        self.assertTrue("180.0,58.0" in joined or "x2='180.0'" in joined)


    def test_object_export_prunes_text_overlapping_emitted_template_bbox(self) -> None:
        graph = SceneGraph(
            width=520,
            height=360,
            nodes=[
                SceneNode(id='container-detail-region-a', type='region', bbox=[300, 110, 340, 145], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-012'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[400, 160, 432, 280], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-012', type='text', bbox=[320, 284, 420, 304], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Time (years) Low risk High risk', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-ghost-1', type='text', bbox=[350, 128, 378, 142], z_index=4, vector_mode='text_box', confidence=0.9, text_content='1.0'),
                SceneNode(id='text-outside', type='text', bbox=[24, 24, 96, 42], z_index=5, vector_mode='text_box', confidence=0.9, text_content='Outside Label'),
            ],
            region_objects=[
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 300 110 L 340 110 L 340 145 L 300 145 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 400 160 L 432 160 L 432 280 L 400 280 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\\n'.join(fragments)

        self.assertIn("data-template-name='survival_curve'", joined)
        self.assertNotIn("id='text-overlay-012'", joined)
        self.assertNotIn("id='text-overlay-ghost-1'", joined)
        self.assertIn("id='text-outside'", joined)

    def test_object_export_prunes_numeric_tick_within_padded_template_zone(self) -> None:
        graph = SceneGraph(
            width=560,
            height=380,
            nodes=[
                SceneNode(id='container-detail-region-a', type='region', bbox=[300, 110, 340, 145], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-012'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[400, 160, 432, 280], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-012', type='text', bbox=[320, 292, 420, 310], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Time (years) Low risk High risk', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-padded-tick', type='text', bbox=[455, 128, 474, 142], z_index=4, vector_mode='text_box', confidence=0.9, text_content='1.0'),
                SceneNode(id='text-overlay-near-label', type='text', bbox=[454, 168, 520, 186], z_index=5, vector_mode='text_box', confidence=0.9, text_content='C-index'),
                SceneNode(id='text-outside-padded', type='text', bbox=[24, 24, 96, 42], z_index=6, vector_mode='text_box', confidence=0.9, text_content='Outside Label'),
            ],
            region_objects=[
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 300 110 L 340 110 L 340 145 L 300 145 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 400 160 L 432 160 L 432 280 L 400 280 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\n'.join(fragments)

        self.assertIn("data-template-name='survival_curve'", joined)
        self.assertNotIn("id='text-overlay-padded-tick'", joined)
        self.assertIn("id='text-overlay-near-label'", joined)
        self.assertIn("id='text-outside-padded'", joined)

    def test_object_export_prunes_any_text_within_fifteen_pixel_template_padding(self) -> None:
        graph = SceneGraph(
            width=560,
            height=380,
            nodes=[
                SceneNode(
                    id='template-node',
                    type='region',
                    bbox=[300, 110, 432, 280],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#d9e6f2',
                    shape_hint='svg_template',
                    component_role='svg_template:radial_icon',
                ),
                SceneNode(id='text-near-template', type='text', bbox=[438, 150, 452, 164], z_index=3, vector_mode='text_box', confidence=0.9, text_content='ghost'),
                SceneNode(id='text-outside-padding', type='text', bbox=[460, 150, 492, 168], z_index=4, vector_mode='text_box', confidence=0.9, text_content='keep'),
            ],
            region_objects=[
                RegionObject(
                    id='region-template',
                    node_id='template-node',
                    outer_path='M 300 110 L 432 110 L 432 280 L 300 280 Z',
                    holes=[],
                    fill='#d9e6f2',
                    stroke='#334155',
                    metadata={'shape_type': 'svg_template', 'template_name': 'radial_icon', 'template_bbox': [300, 110, 432, 280]},
                ),
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\n'.join(fragments)

        self.assertNotIn("id='text-near-template'", joined)
        self.assertIn("id='text-outside-padding'", joined)

    def test_object_export_prunes_mixed_ocr_garbage_near_template(self) -> None:
        graph = SceneGraph(
            width=560,
            height=380,
            nodes=[
                SceneNode(id='container-detail-region-a', type='region', bbox=[300, 110, 340, 145], z_index=1, vector_mode='region_path', confidence=0.9, fill='#355c9a', group_id='component-text-overlay-012'),
                SceneNode(id='container-detail-region-b', type='region', bbox=[400, 160, 432, 280], z_index=2, vector_mode='region_path', confidence=0.9, fill='#6e3f86', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-012', type='text', bbox=[320, 292, 420, 310], z_index=3, vector_mode='text_box', confidence=0.9, text_content='Time (years) Low risk High risk', group_id='component-text-overlay-012'),
                SceneNode(id='text-overlay-ocr-garbage', type='text', bbox=[444, 204, 510, 218], z_index=4, vector_mode='text_box', confidence=0.9, text_content='0.0 C2 04'),
                SceneNode(id='text-overlay-near-label', type='text', bbox=[454, 168, 532, 186], z_index=5, vector_mode='text_box', confidence=0.9, text_content='C-index metric'),
                SceneNode(id='text-outside-padded', type='text', bbox=[24, 24, 96, 42], z_index=6, vector_mode='text_box', confidence=0.9, text_content='Outside Label'),
            ],
            region_objects=[
                RegionObject(id='region-object-a', node_id='container-detail-region-a', outer_path='M 300 110 L 340 110 L 340 145 L 300 145 Z', holes=[], fill='#355c9a', stroke='#355c9a'),
                RegionObject(id='region-object-b', node_id='container-detail-region-b', outer_path='M 400 160 L 432 160 L 432 280 L 400 280 Z', holes=[], fill='#6e3f86', stroke='#6e3f86'),
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\n'.join(fragments)

        self.assertIn("data-template-name='survival_curve'", joined)
        self.assertNotIn("id='text-overlay-ocr-garbage'", joined)
        self.assertIn("id='text-overlay-near-label'", joined)
        self.assertIn("id='text-outside-padded'", joined)

    def test_object_export_keeps_lightweight_container_overlapping_text(self) -> None:
        graph = SceneGraph(
            width=240,
            height=140,
            nodes=[
                SceneNode(
                    id='region-light-container',
                    type='region',
                    bbox=[20, 20, 150, 68],
                    z_index=1,
                    vector_mode='region_path',
                    confidence=0.9,
                    fill='#f6f3ea',
                    stroke='#9aa3ad',
                    group_id='component-region-001',
                    component_role='container_shape',
                ),
                SceneNode(
                    id='text-light-container',
                    type='text',
                    bbox=[28, 30, 138, 54],
                    z_index=2,
                    vector_mode='text_box',
                    confidence=0.9,
                    text_content='Data Sources',
                ),
            ],
            region_objects=[
                RegionObject(
                    id='region-object-light-container',
                    node_id='region-light-container',
                    outer_path='M 20 20 L 150 20 L 150 68 L 20 68 Z',
                    holes=[],
                    fill='#f6f3ea',
                    stroke='#9aa3ad',
                    metadata={
                        'shape_type': 'rectangle',
                        'rectangle': {'x': 20.0, 'y': 20.0, 'width': 130.0, 'height': 48.0},
                    },
                )
            ],
        )

        fragments = export_object_scene_graph(graph)
        joined = '\\n'.join(fragments)

        self.assertIn("id='region-object-light-container'", joined)
        self.assertIn("id='text-light-container'", joined)

if __name__ == '__main__':
    unittest.main()


