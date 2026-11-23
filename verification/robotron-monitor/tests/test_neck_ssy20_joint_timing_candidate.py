"""Verify the alternate SSY20 timing envelope against both cited comparisons."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_ssy20_joint_timing_candidate as screen


class SSY20JointTimingCandidateTests(unittest.TestCase):
    def test_all_switching_and_ac_corners(self):
        report = screen.run()
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['switching_cases']), 128)
        self.assertEqual(report['switching_failures'], 0)
        self.assertEqual(len(report['ac_cases']), 8)
        self.assertEqual(report['ac_comparator_failures'], 0)
        self.assertGreater(report['ac_worst_ft_hz'], 250e6)
        self.assertFalse(report['bounds_promoted'])
        self.assertFalse(report['connected_stress_checked'])


if __name__ == '__main__':
    unittest.main()
