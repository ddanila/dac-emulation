"""Keep V18 gain roll-off and saturation bounds tied to the live model."""
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_output_bjt_bounds as audit


class HorizontalOutputBjtBoundsTests(unittest.TestCase):
    def test_live_v18_corners_match_saved_class_audit(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-output-bjt-bounds.json').read_text())
        self.assertEqual(audit.run(), saved)
        self.assertTrue(saved['passed'])
        self.assertEqual(len(saved['gain_corner_cases']), 4)
        self.assertGreaterEqual(min(row['hFE_4p5a'] for row in saved['gain_corner_cases']), 5)
        self.assertLessEqual(saved['maximum_series_resistance_case']['VCEsat_v'], 1)
        self.assertLessEqual(saved['maximum_series_resistance_case']['VBEsat_v'], 1.1)


if __name__ == '__main__':
    unittest.main()
