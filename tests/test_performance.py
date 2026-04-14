import unittest

from tests.e2e_utils import measure_pipeline_stage_timings, sample_image_path


class PerformanceBudgetTest(unittest.TestCase):
    def test_signature_sample_stays_within_budget(self) -> None:
        timings = measure_pipeline_stage_timings(sample_image_path("orr_signature.png"))

        self.assertLessEqual(timings["analyze_sec"], 1.0)
        self.assertLessEqual(timings["ocr_sec"], 8.0)
        self.assertLessEqual(timings["stage1_sec"], 4.0)
        self.assertLessEqual(timings["total_sec"], 15.0)

    def test_article_figure_sample_stays_within_budget(self) -> None:
        timings = measure_pipeline_stage_timings(sample_image_path("13046_2025_3555_Fig1_HTML.jpg"))

        self.assertLessEqual(timings["ocr_sec"], 10.0)
        self.assertLessEqual(timings["stage1_sec"], 5.0)
        self.assertLessEqual(timings["stage3_sec"], 4.0)
        self.assertLessEqual(timings["total_sec"], 22.0)

    def test_network_sample_stays_within_budget(self) -> None:
        timings = measure_pipeline_stage_timings(sample_image_path("a22efeb2-370f-4745-b79c-474a00f105f4.png"))

        self.assertLessEqual(timings["ocr_sec"], 9.0)
        self.assertLessEqual(timings["stage2_detect_sec"], 7.0)
        self.assertLessEqual(timings["scene_graph_sec"], 6.0)
        self.assertLessEqual(timings["total_sec"], 30.0)
