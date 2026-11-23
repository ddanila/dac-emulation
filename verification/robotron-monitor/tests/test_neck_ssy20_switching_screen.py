"""Check the SSY20 switching fixture against current model bounds."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_ssy20_switching_screen as screen


class SSY20SwitchingScreenTests(unittest.TestCase):
    def test_joint_dynamic_envelope(self):
        report = screen.run()
        self.assertTrue(report['passed'])
        self.assertTrue(report['nominal']['source_limits_met'])
        self.assertFalse(report['old_all_maximum']['source_limits_met'])
        self.assertEqual(report['candidate_corner_count'], 128)
        self.assertEqual(report['candidate_failures'], 0)
        self.assertLessEqual(report['candidate_worst_on_ns'], 50)
        self.assertLessEqual(report['candidate_worst_off_ns'], 100)
        self.assertTrue(report['bounds_promoted'])


if __name__ == '__main__':
    unittest.main()
