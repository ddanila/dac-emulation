"""The 723-family load check must reject the former under-driven proxy."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maa723_model_check as check


class MAA723ModelTests(unittest.TestCase):
    def test_saved_class_response_matches_live_model(self):
        saved = json.loads((ROOT/'reference/k7222-11/maa723-model-check.json').read_text())
        self.assertEqual(saved, check.run())
        self.assertTrue(saved['passed'])

    def test_old_drive_would_fail_50ma_load(self):
        _, entry = check.registered_parameters()
        parameters = json.loads(json.dumps(entry['parameters']))
        parameters['m723_error_gm']['nominal'] = 0.001
        parameters['m723_drive_limit']['nominal'] = 0.0002
        weak = check.op(parameters, supply=12, load_ohm=100)
        self.assertLess(weak['output_v'], 4.9)


if __name__ == '__main__':
    unittest.main()
