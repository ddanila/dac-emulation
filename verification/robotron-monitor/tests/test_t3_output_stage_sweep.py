"""Check the representative loaded T3 result and its reported limits."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_output_stage_sweep as sweep
import transformer_candidates


class T3OutputStageSweepTests(unittest.TestCase):
    def test_1768_turn_stage_has_retrace_but_low_eht(self):
        saved = json.loads((ROOT/'reference/k7222-11/t3-output-stage-sweep.json').read_text())
        self.assertEqual(saved['status'], 'complete')
        self.assertTrue(saved['analysis_valid'])
        self.assertEqual((saved['completed_cases'], saved['aborted_cases']), (32, 0))
        self.assertFalse(saved['joint_collector_eht_comparator_matches'])
        self.assertFalse(saved['documented_eht_matches'])
        graph = json.loads(sweep.GRAPH.read_text())
        parameters = copy.deepcopy(json.loads(sweep.AC_LOSS.read_text()))
        parameters['groups']['high_voltage'][0]['turns']['value'] = 1768
        _, parts, l3_r, l3_l = sweep.source_parts()
        accepted = set(json.loads(sweep.SIGN.read_text())['accepted_candidate_ids'])
        candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                         if item['id'] in accepted)
        result = sweep.simulate(graph, parameters, candidate, parts, l3_r, l3_l)
        self.assertEqual(result['status'], 'complete')
        self.assertGreaterEqual(result['collector_peak_v'], 370)
        self.assertLessEqual(result['collector_peak_v'], 420)
        self.assertGreater(result['flyback_width_us_at_10pct_swing_median'], 15)
        self.assertLess(result['flyback_width_us_at_10pct_swing_median'], 17)
        self.assertLess(result['eht_final_v'], 11500)
        reference = next(row['result'] for row in saved['candidate_results']
                         if row['candidate_id'] == candidate['id'] and row['high_voltage_turns'] == 1768)
        self.assertAlmostEqual(result['eht_final_v'], reference['eht_final_v'], delta=1)


if __name__ == '__main__':
    unittest.main()
