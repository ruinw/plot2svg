import unittest

from plot2svg.template_optimizer import (
    apply_template_optimization,
    dedupe_text_placeholders,
    normalize_component_z_order,
    snap_aligned_bboxes,
)


class TemplateOptimizerTest(unittest.TestCase):
    def test_dedupe_text_placeholders_removes_highly_overlapping_duplicate(self) -> None:
        entries = [
            {
                'display_id': 'TXT001',
                'source_kind': 'node',
                'component_type': 'text',
                'bbox': [10, 10, 60, 30],
                'confidence': 0.80,
            },
            {
                'display_id': 'TXT002',
                'source_kind': 'node',
                'component_type': 'text',
                'bbox': [12, 11, 62, 31],
                'confidence': 0.95,
            },
            {
                'display_id': 'REG001',
                'source_kind': 'node',
                'component_type': 'region',
                'bbox': [80, 10, 120, 50],
            },
        ]

        deduped = dedupe_text_placeholders(entries)

        self.assertEqual([entry['display_id'] for entry in deduped], ['TXT002', 'REG001'])
        self.assertEqual(deduped[0]['optimization_hints']['deduped_from'], ['TXT001'])

    def test_snap_aligned_bboxes_aligns_close_left_edges(self) -> None:
        entries = [
            {'display_id': 'REG001', 'component_type': 'region', 'bbox': [20, 10, 80, 40]},
            {'display_id': 'REG002', 'component_type': 'region', 'bbox': [23, 60, 83, 90]},
            {'display_id': 'REG003', 'component_type': 'region', 'bbox': [150, 10, 190, 40]},
        ]

        snapped = snap_aligned_bboxes(entries, tolerance=4)

        self.assertEqual(snapped[0]['bbox'][0], 20)
        self.assertEqual(snapped[1]['bbox'][0], 20)
        self.assertEqual(snapped[1]['optimization_hints']['snapped_left_to'], 20)
        self.assertEqual(snapped[2]['bbox'][0], 150)

    def test_normalize_component_z_order_places_text_after_shapes(self) -> None:
        entries = [
            {'display_id': 'TXT001', 'component_type': 'text', 'bbox': [10, 10, 50, 24]},
            {'display_id': 'REG001', 'component_type': 'region', 'bbox': [0, 0, 80, 40]},
            {'display_id': 'EDG001', 'component_type': 'edge', 'bbox': [20, 20, 100, 20]},
        ]

        ordered = normalize_component_z_order(entries)

        self.assertEqual([entry['display_id'] for entry in ordered], ['REG001', 'EDG001', 'TXT001'])

    def test_apply_template_optimization_none_bypasses_entries(self) -> None:
        manifest = {
            'version': 1,
            'canvas': {'width': 100, 'height': 60},
            'components': [
                {'display_id': 'TXT001', 'component_type': 'text', 'bbox': [10, 10, 60, 30]},
                {'display_id': 'TXT002', 'component_type': 'text', 'bbox': [12, 11, 62, 31]},
            ],
        }

        optimized = apply_template_optimization(manifest, mode='none')

        self.assertEqual(optimized['components'], manifest['components'])

    def test_apply_template_optimization_deterministic_updates_components(self) -> None:
        manifest = {
            'version': 1,
            'canvas': {'width': 100, 'height': 60},
            'components': [
                {'display_id': 'TXT001', 'component_type': 'text', 'bbox': [10, 10, 60, 30], 'confidence': 0.7},
                {'display_id': 'TXT002', 'component_type': 'text', 'bbox': [12, 11, 62, 31], 'confidence': 0.9},
            ],
        }

        optimized = apply_template_optimization(manifest, mode='deterministic')

        self.assertEqual([entry['display_id'] for entry in optimized['components']], ['TXT002'])
        self.assertEqual(optimized['summary']['component_count'], 1)

if __name__ == '__main__':
    unittest.main()