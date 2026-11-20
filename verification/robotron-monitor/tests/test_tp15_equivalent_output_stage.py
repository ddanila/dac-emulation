"""Keep the apparent TP15/EHT match and its reverse-base violation visible."""
import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tp15_equivalent_output_stage as sweep
import transformer_candidates


class Tp15EquivalentOutputStageTests(unittest.TestCase):
    def test_focus_voltage_match_exceeds_v18_class_rating(self):
        saved = json.loads((ROOT/'reference/k7222-11/tp15-equivalent-output-stage.json').read_text())
        self.assertEqual(saved['v18_emitter_base_reverse_class_limit_v'], 9)
        self.assertEqual(saved['focus_2035_turn_case']['result']['status'], 'complete')
        self.assertGreater(saved['voltage_match_case_count'], 0)
        self.assertEqual(saved['joint_safe_case_count'], 0)
        for name, digest in saved['source_hashes'].items():
            self.assertEqual(sweep.stage.sha(ROOT/name), digest)

        graph = json.loads(sweep.stage.GRAPH.read_text())
        parameters = copy.deepcopy(json.loads(sweep.stage.AC_LOSS.read_text()))
        parameters['groups']['high_voltage'][0]['turns']['value'] = 2035
        _, output_parts, l3_r, l3_l = sweep.stage.source_parts()
        v18 = next(part for part in output_parts
                   if part['source_id'] == '012-6921:V18')
        self.assertEqual(v18['nodes'], ['h_hot', 'h_outbase', '0'])
        driver_parts = sweep.driver.source_parts()
        accepted = set(json.loads(sweep.stage.SIGN.read_text())['accepted_candidate_ids'])
        candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                         if item['id'] in accepted)
        actual = sweep.simulate(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, ratio=1,
                                phase='on_trace', polarity='model')
        expected = saved['focus_2035_turn_case']['result']
        self.assertEqual(actual['status'], 'complete')
        self.assertAlmostEqual(actual['eht_final_v'], expected['eht_final_v'], delta=1)
        self.assertAlmostEqual(actual['collector_peak_v'], expected['collector_peak_v'], delta=1)
        self.assertAlmostEqual(actual['output_base_range_v'][0],
                               expected['output_base_range_v'][0], delta=.1)
        self.assertGreaterEqual(actual['eht_final_v'], 11000)
        self.assertLessEqual(actual['eht_final_v'], 12000)
        self.assertLess(actual['output_base_range_v'][0], -9)


if __name__ == '__main__':
    unittest.main()
