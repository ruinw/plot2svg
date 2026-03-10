from pathlib import Path
import unittest

from plot2svg.segment import (
    ComponentProposal,
    classify_component_role,
    compress_proposals,
    get_proposal_resize_scale,
    propose_components,
    resolve_proposal_max_side,
)
from plot2svg.config import PipelineConfig


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

    def test_propose_components_limits_fragment_count_for_wide_sample(self) -> None:
        output_dir = Path("outputs/test-segment-wide")
        proposals = propose_components(Path("picture/F2.png"), output_dir)
        self.assertLess(len(proposals), 300)
        self.assertGreater(len(proposals), 10)
        self.assertGreaterEqual(sum(1 for item in proposals if item.proposal_type == "text_like"), 60)

    def test_get_proposal_resize_scale_downsamples_wide_images(self) -> None:
        self.assertLess(get_proposal_resize_scale(7680, 2653), 1.0)
        self.assertEqual(get_proposal_resize_scale(635, 568), 1.0)

    def test_speed_profile_uses_smaller_proposal_side_than_quality(self) -> None:
        speed = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="speed")
        quality = PipelineConfig(input_path=Path("picture/F2.png"), output_dir=Path("outputs/F2"), execution_profile="quality")
        self.assertLess(resolve_proposal_max_side(speed), resolve_proposal_max_side(quality))


if __name__ == "__main__":
    unittest.main()
