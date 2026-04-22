import json
from pathlib import Path
import unittest

from plot2svg.component_manifest import build_component_manifest, write_component_manifest
from plot2svg.scene_graph import GraphEdge, IconObject, RasterObject, RegionObject, SceneGraph, SceneGroup, SceneNode


class ComponentManifestTest(unittest.TestCase):
    def test_build_component_manifest_assigns_stable_display_ids(self) -> None:
        graph = SceneGraph(
            width=200,
            height=120,
            nodes=[
                SceneNode(id='background-root', type='background', bbox=[0, 0, 200, 120], z_index=0, vector_mode='region_path', confidence=1.0),
                SceneNode(id='region-2', type='region', bbox=[70, 20, 110, 60], z_index=2, vector_mode='region_path', confidence=0.8, source_mask='masks/r2.png'),
                SceneNode(id='text-1', type='text', bbox=[12, 10, 52, 28], z_index=1, vector_mode='text_box', confidence=0.9, text_content='Label'),
                SceneNode(id='stroke-1', type='stroke', bbox=[20, 70, 120, 72], z_index=3, vector_mode='stroke_path', confidence=0.7),
            ],
            groups=[
                SceneGroup(id='component-region-2', role='labeled_region', bbox=[12, 10, 110, 60], child_ids=['region-2', 'text-1']),
            ],
            region_objects=[
                RegionObject(id='region-object-2', node_id='region-2', outer_path='M 70 20 L 110 20 L 110 60 L 70 60 Z', holes=[]),
            ],
            icon_objects=[
                IconObject(id='icon-object-1', node_id='region-icon', bbox=[130, 20, 170, 60], compound_path='M 130 20 L 170 20 L 170 60 L 130 60 Z'),
            ],
            raster_objects=[
                RasterObject(id='raster-object-1', node_id='region-raster', bbox=[20, 80, 60, 112], image_href='data:image/png;base64,AAAA'),
            ],
            graph_edges=[
                GraphEdge(id='graph-edge-1', source_id='region-2', target_id='region-icon', path=[[110.0, 40.0], [130.0, 40.0]]),
            ],
        )

        manifest = build_component_manifest(graph)

        self.assertEqual(manifest['version'], 1)
        self.assertEqual(manifest['canvas'], {'width': 200, 'height': 120})
        entries = manifest['components']
        self.assertEqual([entry['display_id'] for entry in entries if entry['source_kind'] == 'node'], ['TXT001', 'REG001', 'STK001'])
        self.assertTrue(any(entry['display_id'] == 'GRP001' and entry['svg_id'] == 'component-region-2' for entry in entries))
        self.assertTrue(any(entry['display_id'] == 'ICO001' and entry['source_id'] == 'icon-object-1' for entry in entries))
        self.assertTrue(any(entry['display_id'] == 'RAS001' and entry['source_id'] == 'raster-object-1' for entry in entries))
        self.assertTrue(any(entry['display_id'] == 'EDG001' and entry['source_id'] == 'graph-edge-1' for entry in entries))
        region_entry = next(entry for entry in entries if entry['source_id'] == 'region-2' and entry['source_kind'] == 'node')
        self.assertEqual(region_entry['source_mask'], 'masks/r2.png')
        self.assertEqual(region_entry['bbox'], [70, 20, 110, 60])
        self.assertEqual(region_entry['segmentation_backend'], 'opencv')
        self.assertEqual(region_entry['editable_strategy'], 'native_path')
        self.assertEqual(region_entry['template_id'], 'tpl-REG001')
        self.assertEqual(region_entry['final_svg_id'], 'region-2')
        text_entry = next(entry for entry in entries if entry['source_id'] == 'text-1')
        self.assertEqual(text_entry['editable_strategy'], 'native_text')
        raster_entry = next(entry for entry in entries if entry['source_kind'] == 'raster_object')
        self.assertEqual(raster_entry['editable_strategy'], 'raster_fallback')
        self.assertIn('fallback_reason', raster_entry)

    def test_write_component_manifest_writes_json(self) -> None:
        output_path = Path('outputs/test-component-manifest/components.json')
        graph = SceneGraph(
            width=20,
            height=10,
            nodes=[
                SceneNode(id='text-1', type='text', bbox=[1, 2, 8, 6], z_index=0, vector_mode='text_box', confidence=0.9, text_content='A'),
            ],
        )

        write_component_manifest(graph, output_path)

        payload = json.loads(output_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['components'][0]['display_id'], 'TXT001')
        self.assertEqual(payload['components'][0]['svg_id'], 'text-1')


if __name__ == '__main__':
    unittest.main()
