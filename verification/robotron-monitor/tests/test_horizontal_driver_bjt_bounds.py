"""Keep selected V13 gain, fT and saturation corners tied to the live model."""
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_driver_bjt_bounds as audit


class HorizontalDriverBjtBoundsTests(unittest.TestCase):
    def test_selected_corners_match_saved_class_receipt(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-driver-bjt-bounds.json').read_text())
        self.assertEqual(audit.run(), saved)
        self.assertTrue(saved['selected_corners_pass'])
        self.assertEqual(len(saved['cases']), 5)
        self.assertLessEqual(max(row['VCEsat_v'] for row in saved['cases']), .5)
        self.assertGreaterEqual(min(row['fT_proxy_hz'] for row in saved['cases']), 60e6)


if __name__ == '__main__':
    unittest.main()
