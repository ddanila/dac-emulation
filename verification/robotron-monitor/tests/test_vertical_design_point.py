import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import vertical_design_point as design


class VerticalDesignPointTests(unittest.TestCase):
    def test_report_reproduces_conditional_current_and_design_summary(self):
        report=design.run()
        path=ROOT/'reference/k7222-11/vertical-design-point.json'
        self.assertEqual(report,json.loads(path.read_text()))
        summary=json.loads((ROOT/'reference/k7222-11/design-point.json').read_text())['vertical_yoke_conditional']
        self.assertEqual(summary['report_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertAlmostEqual(summary['nominal_peak_yoke_current_a'],
                               report['nominal']['peak_current_a'])
        self.assertTrue(report['manual_yoke_terminal_guidelines']['inside_toleranced_possibility'])
        sense=report['manual_yoke_terminal_guidelines']['tp7_sense_branch']
        self.assertAlmostEqual(sense['nominal_total_return_current_swing_a'],2.5/3.9)
        self.assertLess(sense['tolerated_total_return_current_swing_a'][0],
                        sense['geometry_yoke_current_swing_a'])
        self.assertGreater(sense['tolerated_total_return_current_swing_a'][1],
                           sense['geometry_yoke_current_swing_a'])
        self.assertEqual(summary['tp7_total_sense_current_swing_a']['nominal'],
                         sense['nominal_total_return_current_swing_a'])

    def test_height_and_eht_change_required_current_in_expected_direction(self):
        report=json.loads((ROOT/'reference/k7222-11/vertical-design-point.json').read_text())
        heights=[case['peak_current_a'] for case in report['height_cases']]
        eht=[case['peak_current_a'] for case in report['eht_cases']]
        self.assertEqual(heights,sorted(heights))
        self.assertEqual(eht,sorted(eht))
        self.assertTrue(all(.2<current<.4 for current in heights+eht))
        refined=[case['peak_current_a'] for case in report['trajectory_refinement']]
        self.assertLess(max(refined)-min(refined),1e-6)
        voltage=report['nominal']['voltage_budget']
        self.assertAlmostEqual(voltage['total_swing_v'],
                               voltage['maximum_v']-voltage['minimum_v'])


if __name__=='__main__':
    unittest.main()
