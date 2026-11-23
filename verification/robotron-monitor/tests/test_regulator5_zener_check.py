import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import regulator5_zener_check as zener


class Regulator5ZenerCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_class_comparison(self):
        report = zener.run()
        saved = report
        self.assertTrue(report['measurement']['passed'])

    def test_wrong_breakdown_voltage_fails(self):
        line = zener.model_line(zener.MODEL.read_text())
        changed = line.replace('BV=5.1', 'BV=6.2')
        self.assertNotEqual(changed, line)
        report = zener.compare(changed)
        self.assertFalse(report['checks']['voltage_at_5ma'])
        self.assertFalse(report['passed'])


if __name__ == '__main__':
    unittest.main()
