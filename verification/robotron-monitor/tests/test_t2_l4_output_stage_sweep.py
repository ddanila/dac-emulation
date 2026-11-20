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
        self.assertEqual((saved['completed_cases'], saved['aborted_cases']), (24, 0))
        self.assertEqual((saved['strict_completed_cases'], saved['relaxed_completed_cases']),
                         (11, 24))
        self.assertEqual(saved['strict_relaxed_comparison_cases'], 11)
        self.assertTrue(saved['strict_relaxed_within_2pct'])
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
        reference = saved['nominal_off_trace_case']
        self.assertEqual(reference['solver']['strict_status'], 'aborted')
        self.assertEqual(reference['solver']['relaxed_status'], 'complete')
        result = sweep.simulate(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, ratio=3, l4_h=5e-6,
                                on_trace=False,
                                reltol=reference['solver']['selected_reltol'])
        self.assertEqual(result['status'], 'complete')
        self.assertLess(result['driver_collector_swing_v'], 36)
        self.assertLess(result['eht_final_v'], 11000)
        reference = reference['result']
        self.assertAlmostEqual(result['driver_collector_swing_v'],
                               reference['driver_collector_swing_v'], delta=.1)
        self.assertAlmostEqual(result['eht_final_v'], reference['eht_final_v'], delta=1)

        reversed_result = sweep.simulate(graph, parameters, candidate, output_parts,
                                         l3_r, l3_l, driver_parts, ratio=3,
                                         l4_h=5e-6, on_trace=True,
                                         secondary_reversed=True)
        self.assertEqual(reversed_result['status'], 'complete')
        self.assertLess(reversed_result['driver_collector_swing_v'], 36)
        self.assertLess(reversed_result['eht_final_v'], 11000)
        reversed_reference = next(row['result'] for row in saved['cases']
                                  if row['t2_secondary_polarity'] == 'reversed'
                                  and row['v13_drive_phase'] == 'on_trace'
                                  and row['t2_primary_secondary_ratio'] == 3
                                  and row['l4_inductance_per_coil_h'] == 5e-6)
        self.assertAlmostEqual(reversed_result['eht_final_v'],
                               reversed_reference['eht_final_v'], delta=1)

        recovered_case = next(row for row in saved['cases']
                              if row['t2_secondary_polarity'] == 'model'
                              and row['v13_drive_phase'] == 'on_trace'
                              and row['t2_primary_secondary_ratio'] == 1
                              and row['l4_inductance_per_coil_h'] == 5e-6)
        recovered = sweep.simulate(graph, parameters, candidate, output_parts,
                                   l3_r, l3_l, driver_parts, ratio=1,
                                   l4_h=5e-6, on_trace=True,
                                   reltol=recovered_case['solver']['selected_reltol'])
        self.assertEqual(recovered['status'], 'complete')
        self.assertLess(recovered['driver_collector_swing_v'], 36)
        self.assertLess(recovered['eht_final_v'], 11000)
        recovered_reference = recovered_case['result']
        self.assertAlmostEqual(recovered['eht_final_v'],
                               recovered_reference['eht_final_v'], delta=1)


if __name__ == '__main__':
    unittest.main()
