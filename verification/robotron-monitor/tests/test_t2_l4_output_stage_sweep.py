"""Check the loaded T2/L4 result and preserve its conditional limits."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t2_l4_output_stage_sweep as sweep
import transformer_candidates


class T2L4OutputStageSweepTests(unittest.TestCase):
    def test_nominal_drive_misses_tp15_and_eht(self):
        saved = json.loads((ROOT/'reference/k7222-11/t2-l4-output-stage-sweep.json').read_text())
        self.assertTrue(saved['analysis_valid'])
        self.assertEqual((saved['completed_cases'], saved['aborted_cases']), (5, 7))
        self.assertFalse(saved['conditional_tp15_matches'])
        self.assertFalse(saved['conditional_eht_matches'])

        graph = json.loads(sweep.stage.GRAPH.read_text())
        parameters = copy.deepcopy(json.loads(sweep.stage.AC_LOSS.read_text()))
        parameters['groups']['high_voltage'][0]['turns']['value'] = 1768
        _, output_parts, l3_r, l3_l = sweep.stage.source_parts()
        driver_parts = sweep.source_parts()
        accepted = set(json.loads(sweep.stage.SIGN.read_text())['accepted_candidate_ids'])
        candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                         if item['id'] in accepted)
        result = sweep.simulate(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, ratio=3, l4_h=5e-6,
                                on_trace=False)
        self.assertEqual(result['status'], 'complete')
        self.assertLess(result['driver_collector_swing_v'], 36)
        self.assertLess(result['eht_final_v'], 11000)
        reference = saved['nominal_off_trace_case']['result']
        self.assertAlmostEqual(result['driver_collector_swing_v'],
                               reference['driver_collector_swing_v'], delta=.1)
        self.assertAlmostEqual(result['eht_final_v'], reference['eht_final_v'], delta=1)


if __name__ == '__main__':
    unittest.main()
