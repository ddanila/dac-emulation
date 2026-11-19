import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vertical_diode_check


class VerticalDiodeCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_comparator_dc_results(self):
        report = vertical_diode_check.run()
        saved = json.loads((ROOT/'reference/k7222-11/vertical-diode-dc-check.json').read_text())
        self.assertEqual(report, saved)
        self.assertTrue(all(report['checked'].values()))
        self.assertIn('reverse recovery at data-sheet IF/IR/RL', report['unchecked'])


if __name__ == '__main__':
    unittest.main()
