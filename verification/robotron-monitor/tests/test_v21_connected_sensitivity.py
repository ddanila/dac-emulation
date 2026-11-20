"""Check that V21's bounded connected-stage effect remains visible."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import v21_connected_sensitivity as check


class V21ConnectedSensitivityTests(unittest.TestCase):
    def test_live_bounds_match_saved_conditional_stage_response(self):
        saved = json.loads((ROOT/'reference/k7222-11/v21-connected-sensitivity.json').read_text())
        live = check.run()
        self.assertEqual(live, saved)
        self.assertEqual((live['completed_bounds'], live['total_bounds']), (24, 24))
        self.assertLess(max(abs(value) for value in
                            live['sense_probe_relative_difference_from_unsensed_stage'].values()), .01)
        slow = next(row for row in live['bounds']
                    if row['parameter'] == 'TT' and row['endpoint'] == 'high')
        self.assertLess(slow['relative_change']['eht_final_v'], -.02)
        self.assertGreater(live['nominal']['stress']['late_window_reverse_voltage_peak_v'], 11000)
        self.assertEqual(live['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
