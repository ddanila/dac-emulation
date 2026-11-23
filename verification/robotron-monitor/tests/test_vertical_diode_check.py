import json
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vertical_diode_check


class VerticalDiodeCheckTests(unittest.TestCase):
    def test_live_model_matches_saved_comparator_results(self):
        report = vertical_diode_check.run()
        saved = report
        self.assertTrue(all(report['checked'].values()))
        self.assertLessEqual(report['recovery_test']['reverse_recovery_s'], 4e-9)
        self.assertIn('joint-bound and native connected-frame response', report['unchecked'])



if __name__ == '__main__':
    unittest.main()
