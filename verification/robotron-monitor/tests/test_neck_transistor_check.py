import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_transistor_check


class NeckTransistorCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_data_sheet_dc_comparison(self):
        report = neck_transistor_check.run()
        saved = report
        for case in report['cases'].values():
            self.assertTrue(case['gain_in_group_A_range'])
            self.assertTrue(case['saturation_below_1_v'])
            self.assertAlmostEqual(case['gain_bias']['collector_current_a'], .5, delta=1e-5)
            self.assertAlmostEqual(case['saturation_bias']['collector_current_a'], .5,
                                   delta=1/80)
        self.assertTrue(all(corner['within_group_A'] for corner in
                            report['joint_bf_ikf_gain_corners']))
        self.assertTrue(report['high_series_resistance_saturation']['below_1_v'])


if __name__ == '__main__':
    unittest.main()
