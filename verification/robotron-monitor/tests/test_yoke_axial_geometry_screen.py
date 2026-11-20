import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import yoke_axial_geometry_screen as screen


class YokeAxialGeometryScreenTests(unittest.TestCase):
    def test_shorter_tube_class_changes_required_field_extent(self):
        sources = ROOT.parents[1]/'build/monitor/phase-a/sources'
        actual = screen.run(
            sources/'1987_T16_Philips_Monochrome_Tubes_and_Deflection_Units.pdf',
            sources/'k7222_61.pdf', sources/'crt_m31-proxy-original',
            sources/'older.pdf')
        saved = json.loads((ROOT/'reference/k7222-11/yoke-axial-geometry-screen.json').read_text())
        self.assertEqual(actual, saved)
        self.assertGreater(actual['class_comparison']['active_gun_to_screen_m'],
                           actual['class_comparison']['b31_g_family_maximum_overall_length_m'])
        cases = {(row['screen_z_m'], row['field_length_m']): row
                 for row in actual['cases']}
        self.assertFalse(cases[(.23, .0347)]['reaches_210mm_width'])
        self.assertTrue(cases[(.23, .025)]['reaches_210mm_width'])
        self.assertTrue(cases[(.23, .025)]['inside_90_degree_yoke_current_proxy'])
        self.assertTrue(cases[(.25, .0275)]['reaches_210mm_width'])
        self.assertFalse(cases[(.25, .03)]['reaches_210mm_width'])
        self.assertFalse(cases[(.20, .020)]['inside_90_degree_yoke_current_proxy'])
        thresholds = {row['screen_z_m']: row
                      for row in actual['conditional_field_length_thresholds']}
        self.assertTrue(.0265 < thresholds[.23]['maximum_field_length_m'] < .0266)
        self.assertTrue(.029 < thresholds[.25]['maximum_field_length_m'] < .030)
        self.assertTrue(.0216 < thresholds[.20]['maximum_field_length_m'] < .0217)
        design = json.loads((ROOT/'reference/k7222-11/design-point.json').read_text())
        self.assertEqual(design['conditional_axial_geometry_screen']['conditional_maximum_field_length_m_at_230mm_path'],
                         thresholds[.23]['maximum_field_length_m'])
        self.assertEqual(design['conditional_axial_geometry_screen']['conditional_maximum_field_length_m_at_250mm_path'],
                         thresholds[.25]['maximum_field_length_m'])
        self.assertEqual(design['conditional_axial_geometry_screen']['conditional_maximum_field_length_m_at_200mm_path'],
                         thresholds[.20]['maximum_field_length_m'])
        self.assertEqual(design['geometry_diagnostic']['tube_outline_candidate']['b31_g_maximum_overall_length_m'],
                         actual['class_comparison']['b31_g_family_maximum_overall_length_m'])


if __name__ == '__main__':
    unittest.main()
