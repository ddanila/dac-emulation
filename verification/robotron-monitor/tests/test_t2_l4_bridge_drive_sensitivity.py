"""Check the saved conditional bridge drive/turn boundary."""
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t2_l4_bridge_drive_sensitivity as sensitivity
import transformer_candidates


class T2L4BridgeDriveSensitivityTests(unittest.TestCase):
    def test_high_tp15_drive_does_not_rescue_eht_or_v18_stress(self):
        saved = json.loads(sensitivity.REPORT.read_text())
        self.assertEqual(saved['completed_cases'], 7)
        self.assertEqual(saved['joint_eht_reverse_base_cases'], 0)
        for name, digest in saved['source_hashes'].items():
            self.assertEqual(sensitivity.l4.stage.sha(ROOT/name), digest)

        stage = sensitivity.l4.stage
        graph = json.loads(stage.GRAPH.read_text())
        initial = json.loads(stage.AC_LOSS.read_text())
        _, output_parts, l3_r, l3_l = stage.source_parts()
        driver_parts = sensitivity.l4.driver.source_parts()
        accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
        candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                         if item['id'] in accepted)
        actual = sensitivity.simulate(graph, initial, candidate, output_parts,
                                      l3_r, l3_l, driver_parts, 2035, 54)
        expected = next(row['result'] for row in saved['cases']
                        if row['hv_turns'] == 2035
                        and row['tp15_source_swing_vpp'] == 54)
        self.assertEqual(actual['status'], 'complete')
        self.assertAlmostEqual(actual['eht_final_v'], expected['eht_final_v'], delta=2)
        self.assertAlmostEqual(actual['output_base_range_v'][0],
                               expected['output_base_range_v'][0], delta=.1)
        self.assertLess(actual['eht_final_v'], saved['manual_eht_range_v'][0])
        self.assertLess(actual['output_base_range_v'][0],
                        -saved['v18_reverse_base_class_limit_v'])


if __name__ == '__main__':
    unittest.main()
