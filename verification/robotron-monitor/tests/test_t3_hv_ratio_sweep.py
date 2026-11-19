"""Keep the conditional T3 ratio diagnostic tied to the live design point."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import t3_hv_ratio_sweep


class T3HVRatioSweepTests(unittest.TestCase):
    def test_current_hypothesis_misses_conditional_ratio(self):
        report=t3_hv_ratio_sweep.run()
        saved=json.loads((ROOT/'reference/k7222-11/t3-hv-ratio-sweep.json').read_text())
        self.assertEqual(report,saved)
        self.assertTrue(report['passed'])
        target=report['conditional_ratio_from_design_point']
        self.assertLess(report['cases']['current']['ideal_open_circuit_ratio'],
                        target['minimum'])
        self.assertLess(report['cases']['current']['isolated_window_mean_ratio'],
                        target['minimum'])
        candidate=report['cases']['conditional_nominal']
        self.assertTrue(target['minimum']<=candidate['ideal_open_circuit_ratio']<=target['maximum'])
        design=json.loads((ROOT/'reference/k7222-11/design-point.json').read_text())
        scale=design['conditional_t3_hv_turn_scale']
        self.assertEqual(scale['assumed_drive_total_turns'],report['assumed_drive_total_turns'])
        self.assertEqual(scale['current_hv_turns'],report['cases']['current']['turns'])
        self.assertEqual(scale['current_ideal_open_circuit_ratio'],
                         report['cases']['current']['ideal_open_circuit_ratio'])
        self.assertEqual(scale['candidate_hv_turns_if_current_drive_scale_and_boost_case_hold'],
                         {'minimum':report['cases']['conditional_lower']['turns'],
                          'nominal':report['cases']['conditional_nominal']['turns'],
                          'maximum':report['cases']['conditional_upper']['turns']})
        self.assertIn('no loaded EHT',report['qualification'])


if __name__=='__main__':unittest.main()
