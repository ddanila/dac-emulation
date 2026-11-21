"""The saved MAA723 corner result must follow the live internal models."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maa723_internal_corner_screen as screen


class MAA723InternalCornerTests(unittest.TestCase):
    def test_saved_screen_and_pass_device_dependency(self):
        saved = json.loads((ROOT/'reference/k7222-11/maa723-internal-corner-screen.json').read_text())
        self.assertEqual(saved, screen.run())
        self.assertEqual(saved['cases'], 9)
        self.assertEqual(saved['class_check_failures_at_25c'], 0)
        self.assertEqual(saved['engineering_probe_misses_at_25c'], 4)
        self.assertEqual(saved['lower_dissipation_probe_misses_at_25c'], 4)
        attribution = saved['pass_corner_attribution']
        restored = attribution['restore_nominal_from_all_low_pass_load_current_a']
        self.assertLess(restored['none'], .063)
        self.assertLess(restored['BF'], .100)
        self.assertLess(restored['IKF'], .100)
        self.assertGreater(restored['BF+IKF'], .145)
        self.assertLess(attribution['low_bf_ikf_drive_ceiling_sweep']['high']['load_current_a'], .100)
        nominal_probe = saved['rows'][0]['temperatures'][1]['lower_dissipation_150ma_probe']
        self.assertGreater(nominal_probe['actual_load_current_a'], .145)
        self.assertLess(nominal_probe['chip_power_proxy_w'], .66)
        for row in saved['rows'][1:]:
            self.assertTrue(row['class_checks_at_25c_pass'])
            self.assertEqual(row['engineering_4p9v_probe_at_25c_pass'],
                             row['groups']['M723_PASS'] == 'high')
            self.assertEqual(row['lower_dissipation_145ma_probe_at_25c_pass'],
                             row['groups']['M723_PASS'] == 'high')
            for result in row['temperatures']:
                if row['groups']['M723_PASS'] == 'low':
                    self.assertFalse(result['engineering_150ma_probe']['meets_4p9v_proxy'])
                    self.assertLess(result['engineering_150ma_probe']['actual_load_current_a'], .07)
                    self.assertLess(result['lower_dissipation_150ma_probe']['actual_load_current_a'], .07)


if __name__ == '__main__':
    unittest.main()
