"""Keep the cross-revision winding comparator aligned with the A5 design point."""

import hashlib
import json
from pathlib import Path
import unittest


REF = Path(__file__).resolve().parents[1] / 'reference/k7222-11'


class T3HvWindingComparatorTests(unittest.TestCase):
    def test_conditional_voltage_proxy_is_not_a_turns_inference(self):
        design_path = REF / 'design-point.json'
        design = json.loads(design_path.read_text())
        report = json.loads((REF / 't3-hv-winding-comparator.json').read_text())
        self.assertEqual(report['design_point_sha256'],
                         hashlib.sha256(design_path.read_bytes()).hexdigest())
        ratio = design['high_voltage_ratio']['ratio_if_boost_case_is_correct']
        comparison = report['active_model_comparison']
        self.assertEqual(comparison['conditional_ideal_eht_to_collector_proxy_range'],
                         [ratio['minimum'], ratio['maximum']])
        self.assertAlmostEqual(
            comparison['original_comparator_ratio_over_conditional_proxy_upper_bound'],
            comparison['original_comparator_ideal_hv_to_64_turn_drive_ratio'] /
            ratio['maximum'])
        self.assertNotIn('drive_turns_implied_by_original_comparator_and_conditional_ratio',
                         comparison)
        self.assertEqual(report['derived_comparison']['original_reported_turns'],
                         36 * 66 + 33)
        self.assertEqual(report['derived_comparison']['replacement_reported_turns'],
                         26 * 68)
        register = json.loads((REF / 'device-model-register.json').read_text())
        device = next(row for row in register['devices']
                      if row['id'] == '012-6921:T3')
        self.assertNotIn('conditional_range_if_2409_hv_turns_and_boost_case',
                         device['parameters']['drive_total_turns'])


if __name__ == '__main__':
    unittest.main()
