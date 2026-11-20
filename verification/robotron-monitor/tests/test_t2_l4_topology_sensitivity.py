"""Keep the L4-bridge reverse-base boundary reproducible."""
import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t2_l4_topology_sensitivity as sensitivity
import transformer_candidates


class T2L4TopologySensitivityTests(unittest.TestCase):
    def test_lowest_reverse_stress_case_still_exceeds_v18_class_limit(self):
        saved = json.loads((ROOT/'reference/k7222-11/t2-l4-topology-sensitivity.json').read_text())
        self.assertEqual(saved['completed_cases'], 8)
        self.assertEqual(saved['reverse_base_safe_cases'], 0)
        self.assertEqual(saved['joint_eht_reverse_base_cases'], 0)
        for name, digest in saved['source_hashes'].items():
            self.assertEqual(sensitivity.stage.sha(ROOT/name), digest)

        graph = json.loads(sensitivity.stage.GRAPH.read_text())
        parameters = copy.deepcopy(json.loads(sensitivity.stage.AC_LOSS.read_text()))
        parameters['groups']['high_voltage'][0]['turns']['value'] = 2035
        _, output_parts, l3_r, l3_l = sensitivity.stage.source_parts()
        driver_parts = sensitivity.driver.source_parts()
        accepted = set(json.loads(sensitivity.stage.SIGN.read_text())['accepted_candidate_ids'])
        candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                         if item['id'] in accepted)
        actual = sensitivity.simulate(graph, parameters, candidate, output_parts,
                                      l3_r, l3_l, driver_parts, topology='bridge',
                                      ratio=10)
        expected = next(row['result'] for row in saved['cases']
                        if row['l4_path'] == 'bridge'
                        and row['t2_primary_secondary_ratio'] == 10)
        self.assertEqual(actual['status'], 'complete')
        self.assertAlmostEqual(actual['eht_final_v'], expected['eht_final_v'], delta=1)
        self.assertAlmostEqual(actual['output_base_range_v'][0],
                               expected['output_base_range_v'][0], delta=.1)
        self.assertLess(actual['output_base_range_v'][0],
                        -saved['v18_reverse_base_class_limit_v'])


if __name__ == '__main__':
    unittest.main()
