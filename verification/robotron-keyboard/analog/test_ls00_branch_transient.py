"""Reject incomplete captures and distinguish recovery from a branch transition."""
import unittest
from ls00_branch_transient import summarize


class RecoveryTests(unittest.TestCase):
    def rows(self, final=1):
        return [[0, 0], [8e-7, 1], [9e-7, 1], [1e-6, 1.1],
                [1.8e-6, final], [1.9e-6, final], [2e-6, final]]

    def test_recovery_and_branch_transition(self):
        self.assertEqual(summarize(self.rows(), ['v(y)'])['v(y)']['recoveryDifferenceVolts'], 0)
        self.assertAlmostEqual(summarize(self.rows(.2), ['v(y)'])['v(y)']['recoveryDifferenceVolts'], .8)

    def test_ringing_is_not_a_settled_plateau(self):
        rows = self.rows()
        rows[-2][1] = 1.1
        self.assertGreater(summarize(rows, ['v(y)'])['v(y)']['maximumWindowSpanVolts'], .09)

    def test_incomplete_or_invalid_capture(self):
        for rows in [self.rows()[:-1], self.rows()[:1] + self.rows()[3:],
                     self.rows() + [self.rows()[-1]], self.rows()[:-1] + [[2e-6, float('nan')]]]:
            with self.assertRaises(ValueError):
                summarize(rows, ['v(y)'])


if __name__ == '__main__':
    unittest.main()
