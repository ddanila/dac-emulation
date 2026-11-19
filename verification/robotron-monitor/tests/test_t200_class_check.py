import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import signal_path
import t200_class_check


class T200ClassCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_class_check(self):
        actual = t200_class_check.run()
        saved = json.loads((ROOT/'reference/k7222-11/t200-class-check.json').read_text())
        self.assertEqual(actual, saved)
        self.assertTrue(actual['passed'])
        self.assertTrue(all(actual['checks'].values()))

    def test_every_gate_parameter_is_bounded_and_registered(self):
        register = json.loads((ROOT/'reference/k7222-11/device-model-register.json').read_text())
        device = next(row for row in register['devices'] if row['id'] == '012-6921:A1')
        self.assertEqual(device['model'], 'T200_BOUND')
        live = {key: value for key, value in signal_path.BOUNDS.items()
                if key.startswith('gate_')}
        self.assertEqual(set(device['parameters']), set(live))
        for key, (nominal, minimum, maximum) in live.items():
            self.assertEqual(device['parameters'][key]['nominal'], nominal)
            self.assertEqual(device['parameters'][key]['bounds'], [minimum, maximum])


if __name__ == '__main__':
    unittest.main()
