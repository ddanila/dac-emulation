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
        saved = json.loads((ROOT/'reference/k7222-11/ssy20-model-dc-check.json').read_text())
        self.assertEqual(report, saved)
        for case in report['cases'].values():
            self.assertTrue(case['gain_in_group_A_range'])
            self.assertTrue(case['saturation_below_1_v'])
            self.assertAlmostEqual(case['gain_bias']['collector_current_a'], .5, delta=1e-5)
            self.assertAlmostEqual(case['saturation_bias']['collector_current_a'], .5, delta=.002)


if __name__ == '__main__':
    unittest.main()
