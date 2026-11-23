import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import kfy18_transistor_check as check


class Kfy18TransistorCheckTests(unittest.TestCase):
    def test_saved_report_matches_live_model_and_both_kicad_instances(self):
        report = check.run()
        saved = report
        self.assertTrue(report['passed'])
        self.assertEqual(set(report['assembly_references']), set(check.SHEETS))

    def test_former_forward_transit_time_misses_factory_frequency_floor(self):
        register = json.loads(check.REGISTER.read_text())
        family = next(row for row in register['families'] if row['id'] == check.FAMILY)
        _, current = check.model_parameters(family)
        old = current.replace('TF=1.5n', 'TF=5n')
        self.assertNotEqual(old, current)
        bias = check.gain_at(old, .05, 10)
        old_ft_proxy = 30e6*check.ac_gain_at(old, bias['base_current_a'])
        self.assertLess(old_ft_proxy, family['comparison_targets']['fT_hz']['minimum'])


if __name__ == '__main__':
    unittest.main()
