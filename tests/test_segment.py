from pathlib import Path
import unittest

import cv2
import numpy as np

from plot2svg.segment import (
    ComponentProposal,
    classify_component_role,
    compress_proposals,
    get_proposal_resize_scale,
    propose_components,
    resolve_proposal_max_side,
)
from plot2svg.config import PipelineConfig
from plot2svg.text_layers import separate_text_graphics


class SegmentTest(unittest.TestCase):
    def test_component_proposal_serializes_bbox(self) -> None:
        proposal = ComponentProposal(
            component_id="c1",
            bbox=[0, 0, 10, 10],
            mask_path="masks/c1.png",
            proposal_type="region",
            confidence=0.8,
        )
        self.assertEqual(proposal.to_dict()["bbox"], [0, 0, 10, 10])

    def test_classify_component_role_detects_text_like_shapes(self) -> None:
        role = classify_component_role(width=120, height=18, area=1200)
        self.assertEqual(role, "text_like")

    def test_propose_components_creates_multiple_component_candidates(self) -> None:
        output_dir = Path("outputs/test-segment")
        proposals = propose_components(Path("picture/orr_signature.png"), output_dir)
        self.assertGreaterEqual(len(proposals), 2)
        self.assertTrue((output_dir / "components_raw.json").exists())

    def test_compress_proposals_merges_overlapping_components(self) -> None:
        proposals = [
            ComponentProposal("region-001", [0, 0, 100, 100], "masks/a.png", "region", 0.8),
            ComponentProposal("region-002", [4, 4, 96, 96], "masks/b.png", "region", 0.7),
            ComponentProposal("stroke-003", [150, 150, 170, 170], "masks/c.png", "stroke", 0.9),
        ]
        compressed = compress_proposals(proposals, image_width=200, image_height=200)
        self.assertEqual(len(compressed), 2)
        self.assertTrue(any(item.component_id == "stroke-003" for item in compressed))

    def test_compress_proposals_does_not_merge_shape_hinted_regions(self) -> None:
        proposals = [
            ComponentProposal("region-001", [0, 0, 100, 100], "masks/a.png", "region", 0.95, shape_hint="triangle"),
            ComponentProposal("region-002", [6, 6, 106, 106], "masks/b.png", "region", 0.93, shape_hint="pentagon"),
        ]
        compressed = compress_proposals(proposals, image_width=160, image_height=160)
        self.assertEqual(len(compressed), 2)

    def test_split_component_mask_separates_touching_blobs(self) -> None:
        from plot2svg import segment as segment_module

        mask = np.zeros((120, 180), dtype=np.uint8)
        cv2.circle(mask, (70, 60), 28, 255, -1)
        cv2.circle(mask, (104, 60), 28, 255, -1)

        parts = segment_module._split_component_mask(mask)

        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(np.count_nonzero(part) > 0 for part in parts))

    def test_propose_components_limits_fragment_count_for_wide_sample(self) -> None:
        output_dir = Path("outputs/test-segment-wide")
        proposals = propose_components(Path("picture/F2.png"), output_dir)
        self.assertLess(len(proposals), 400)
        self.assertGreater(len(proposals), 10)
        self.assertGreaterEqual(sum(1 for item in proposals if item.proposal_type == "text_like"), 60)

    def test_propose_components_preserves_circle_hints_for_network_sample(self) -> None:
        output_dir = Path("outputs/test-segment-network")
        proposals = propose_components(Path("picture/a22efeb2-370f-4745-b79c-474a00f105f4.png"), output_dir)
        self.assertGreaterEqual(sum(1 for item in proposals if item.shape_hint == "circle"), 8)

    def test_get_proposal_resize_scale_downsamples_wide_images(self) -> None:
        self.assertLess(get_proposal_resize_scale(7680, 2653), 1.0)
        self.assertEqual(get_proposal_resize_scale(635, 568), 1.0)

    def test_speed_profile_uses_smaller_proposal_side_than_quality(self) -> None:
        speed = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="speed")
        quality = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="quality")
        self.assertLess(resolve_proposal_max_side(speed), resolve_proposal_max_side(quality))

    def test_component_proposal_serializes_shape_hint(self) -> None:
        proposal = ComponentProposal(
            component_id="c2",
            bbox=[0, 0, 10, 10],
            mask_path="masks/c2.png",
            proposal_type="region",
            confidence=0.8,
            shape_hint="circle",
        )
        d = proposal.to_dict()
        self.assertEqual(d["shape_hint"], "circle")

    def test_component_proposal_shape_hint_defaults_none(self) -> None:
        proposal = ComponentProposal(
            component_id="c3",
            bbox=[0, 0, 10, 10],
            mask_path="masks/c3.png",
            proposal_type="region",
            confidence=0.8,
        )
        self.assertIsNone(proposal.shape_hint)

    def test_propose_components_does_not_inject_full_canvas_region_when_strokes_exist(self) -> None:
        image = np.full((180, 220, 3), 255, dtype=np.uint8)
        center = (70, 95)
        for y in [35, 55, 75, 95, 115, 135, 155]:
            cv2.line(image, center, (175, y), (0, 0, 0), 1, cv2.LINE_AA)

        output_dir = Path("outputs/test-segment-radial")
        proposals = propose_components(image, output_dir)

        self.assertTrue(any(item.proposal_type == "stroke" for item in proposals))
        self.assertFalse(any(item.proposal_type == "region" and item.bbox == [0, 0, 220, 180] for item in proposals))

    def test_propose_components_uses_text_layer_to_preserve_text_like_candidates(self) -> None:
        image = np.full((140, 260, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (60, 35), (210, 95), (223, 218, 191), -1)
        cv2.rectangle(image, (60, 35), (210, 95), (154, 144, 110), 2)
        cv2.putText(image, 'Phenotype', (78, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (35, 35, 35), 2, cv2.LINE_AA)
        layers = separate_text_graphics(image)

        output_dir = Path("outputs/test-segment-text-layer")
        proposals = propose_components(layers.graphic_layer, output_dir, text_image_input=layers.text_layer)

        self.assertTrue(any(item.proposal_type == "text_like" for item in proposals))


    def test_dense_detail_cluster_splitter_breaks_micro_contours_into_parts(self) -> None:
        from plot2svg import segment as segment_module

        mask = np.zeros((160, 160), dtype=np.uint8)
        for row in range(3):
            for col in range(4):
                cv2.circle(mask, (28 + col * 28, 36 + row * 28), 7, 255, -1)

        parts = segment_module._split_dense_detail_cluster(mask)

        self.assertGreaterEqual(len(parts), 10)
        self.assertTrue(all(np.count_nonzero(part) > 0 for part in parts))

    def test_compress_proposals_does_not_merge_dense_detail_regions(self) -> None:
        proposals = [
            ComponentProposal('region-001', [0, 0, 80, 80], 'masks/a.png', 'region', 0.9, shape_hint='dense_detail'),
            ComponentProposal('region-002', [6, 6, 86, 86], 'masks/b.png', 'region', 0.88, shape_hint='dense_detail'),
        ]

        compressed = compress_proposals(proposals, image_width=160, image_height=160)

        self.assertEqual(len(compressed), 2)


    def test_cluster_icon_candidate_records_merges_nearby_raster_fragments(self) -> None:
        from plot2svg import segment as segment_module

        mask_a = np.zeros((120, 120), dtype=np.uint8)
        mask_b = np.zeros((120, 120), dtype=np.uint8)
        cv2.rectangle(mask_a, (20, 20), (34, 52), 255, -1)
        cv2.rectangle(mask_b, (40, 24), (58, 56), 255, -1)

        records = [
            segment_module._ProposalRecord([20, 20, 35, 53], 'region', 0.82, mask_a, 'raster_candidate'),
            segment_module._ProposalRecord([40, 24, 59, 57], 'region', 0.84, mask_b, 'raster_candidate'),
        ]

        clustered = segment_module._cluster_icon_candidate_records(records, image_width=120, image_height=120)

        icon_clusters = [item for item in clustered if item.shape_hint == 'icon_cluster']
        self.assertEqual(len(icon_clusters), 1)
        self.assertLessEqual(icon_clusters[0].bbox[0], 20)
        self.assertGreaterEqual(icon_clusters[0].bbox[2], 59)

    def test_cluster_icon_candidate_records_rejects_merge_when_text_overlaps_cluster(self) -> None:
        from plot2svg import segment as segment_module

        mask_a = np.zeros((120, 120), dtype=np.uint8)
        mask_b = np.zeros((120, 120), dtype=np.uint8)
        text_mask = np.zeros((120, 120), dtype=np.uint8)
        cv2.rectangle(mask_a, (20, 20), (34, 52), 255, -1)
        cv2.rectangle(mask_b, (40, 24), (58, 56), 255, -1)
        cv2.rectangle(text_mask, (16, 18), (62, 38), 255, -1)

        records = [
            segment_module._ProposalRecord([20, 20, 35, 53], 'region', 0.82, mask_a, 'raster_candidate'),
            segment_module._ProposalRecord([40, 24, 59, 57], 'region', 0.84, mask_b, 'raster_candidate'),
            segment_module._ProposalRecord([16, 18, 63, 39], 'text_like', 0.9, text_mask, None),
        ]

        clustered = segment_module._cluster_icon_candidate_records(records, image_width=120, image_height=120)

        self.assertFalse(any(item.shape_hint == 'icon_cluster' for item in clustered))
        raster_candidates = [item for item in clustered if item.shape_hint == 'raster_candidate']
        self.assertEqual(len(raster_candidates), 2)

if __name__ == "__main__":
    unittest.main()