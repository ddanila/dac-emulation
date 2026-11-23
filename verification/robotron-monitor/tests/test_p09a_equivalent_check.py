import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import p09a_equivalent_check


class P09AEquivalentTests(unittest.TestCase):
    def test_isolated_class_response_and_registered_model_parameters(self):
        saved = p09a_equivalent_check.run()
        self.assertTrue(saved['passed'])
        self.assertEqual(len(saved['checks']), 8)

        register = json.loads((ROOT / 'reference/k7222-11/device-model-register.json').read_text())
        entry = next(row for row in register['devices'] if row['id'] == '012-6931:A3')
        self.assertEqual(entry['model'], 'P09A_EQUIV')
        text = p09a_equivalent_check.MODEL.read_text()
        parameters = dict(re.findall(r'\b([a-z_]+)=([0-9.eE+-]+)', text))
        self.assertEqual(set(parameters), set(entry['parameters']))
        for key, parameter in entry['parameters'].items():
            self.assertEqual(float(parameters[key]), parameter['nominal'])


if __name__ == '__main__':
    unittest.main()
