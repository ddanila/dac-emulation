"""Keep the SSY20A AC screen tied to the live neck model and comparison bias."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_ssy20_ft_screen as screen


class SSY20FTScreenTests(unittest.TestCase):
    def test_current_ac_corners_and_saved_receipt(self):
        live = screen.run()
        self.assertEqual(live, json.loads(screen.OUTPUT.read_text()))
        self.assertEqual(len(live['cases']), 8)
        self.assertFalse(live['nominal']['meets_bsy34_comparator'])
        self.assertFalse(live['all_corners_meet_comparator'])
        self.assertFalse(live['direct_ssy20_ft_qualified'])
        self.assertTrue(any(row['meets_bsy34_comparator'] for row in live['cases']))
        self.assertTrue(all(abs(row['collector_current_a'] - .03) < 1e-6
                            for row in live['cases']))


if __name__ == '__main__':
    unittest.main()
