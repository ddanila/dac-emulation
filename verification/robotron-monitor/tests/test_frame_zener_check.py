import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frame_zener_check as zener


class FrameZenerCheckTests(unittest.TestCase):
    def test_live_models_match_saved_class_comparison(self):
        report = zener.run()
        saved = json.loads((ROOT/'reference/k7222-11/frame-zener-class-check.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual({row['id'] for row in report['rows']},
                         {'012-6921:V4', '012-6921:V11', '012-6931:V15'})

    def test_wrong_breakdown_voltage_fails(self):
        part, name, relative_path, _, voltage_range, resistance_limit = zener.CASES[0]
        line = zener.model_line(ROOT/relative_path, name)
        changed = line.replace('BV=9.1', 'BV=12')
        self.assertNotEqual(changed, line)
        result = zener.compare(changed, name, voltage_range, resistance_limit)
        self.assertFalse(result['checks']['voltage_at_5ma'])
        self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
