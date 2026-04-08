import unittest

import cv2
import numpy as np

from plot2svg.icon_processor import IconProcessor
from plot2svg.svg_templates import SVG_TEMPLATES, append_template_role, extract_template_name, match_svg_template, render_svg_template


class SvgTemplatesTest(unittest.TestCase):
    def test_static_template_library_contains_required_presets(self) -> None:
        self.assertIn('database', SVG_TEMPLATES)
        self.assertIn('clock', SVG_TEMPLATES)
        self.assertIn('cohort', SVG_TEMPLATES)
        self.assertIn('document', SVG_TEMPLATES)
        self.assertIn('radial_icon', SVG_TEMPLATES)

    def test_append_and_extract_template_role(self) -> None:
        role = append_template_role('container_shape', 'database')
        self.assertEqual(extract_template_name(role), 'database')

    def test_match_svg_template_detects_clock_icon(self) -> None:
        image = np.full((96, 96, 3), 255, dtype=np.uint8)
        cv2.circle(image, (48, 48), 28, (0, 0, 0), 3)
        cv2.line(image, (48, 48), (48, 28), (0, 0, 0), 3, cv2.LINE_AA)
        cv2.line(image, (48, 48), (62, 56), (0, 0, 0), 3, cv2.LINE_AA)
        complexity = IconProcessor().evaluate_complexity(image)

        self.assertEqual(match_svg_template(image, complexity), 'clock')

    def test_match_svg_template_detects_database_icon(self) -> None:
        image = np.full((120, 120, 3), 255, dtype=np.uint8)
        cv2.ellipse(image, (60, 26), (28, 12), 0, 0, 360, (0, 0, 0), 3)
        cv2.line(image, (32, 26), (32, 88), (0, 0, 0), 3)
        cv2.line(image, (88, 26), (88, 88), (0, 0, 0), 3)
        cv2.ellipse(image, (60, 56), (28, 12), 0, 0, 180, (0, 0, 0), 3)
        cv2.ellipse(image, (60, 88), (28, 12), 0, 0, 180, (0, 0, 0), 3)
        complexity = IconProcessor().evaluate_complexity(image)

        self.assertEqual(match_svg_template(image, complexity), 'database')

    def test_render_svg_template_returns_group_fragment(self) -> None:
        fragment = render_svg_template('database', [10, 20, 110, 140], element_id='template-1', node_id='node-1')

        self.assertIsNotNone(fragment)
        self.assertIn("class='svg-template'", fragment)
        self.assertIn("data-template-name='database'", fragment)
        self.assertIn('<svg x="16" y="27" width="88" height="106"', fragment)

    def test_render_svg_template_insets_scientific_templates_more_aggressively(self) -> None:
        fragment = render_svg_template('survival_curve', [100, 200, 300, 500], element_id='template-2', node_id='node-2')

        self.assertIsNotNone(fragment)
        self.assertIn("data-template-name='survival_curve'", fragment)
        self.assertIn('preserveAspectRatio="xMidYMid meet"', fragment)
        self.assertIn('<svg x="140" y="263" width="120" height="174"', fragment)

    def test_match_svg_template_detects_radial_icon(self) -> None:
        image = np.full((429, 135, 3), 255, dtype=np.uint8)
        hub = (125, 211)
        circle_ys = [20, 85, 140, 169, 196, 217, 246, 290, 309, 414]
        for y in circle_ys:
            cv2.circle(image, (24, y), 9, (170, 110, 50), -1)
            cv2.line(image, (33, y), hub, (70, 70, 70), 2, cv2.LINE_AA)
        complexity = IconProcessor().evaluate_complexity(image)

        self.assertEqual(match_svg_template(image, complexity), 'radial_icon')


if __name__ == '__main__':
    unittest.main()
