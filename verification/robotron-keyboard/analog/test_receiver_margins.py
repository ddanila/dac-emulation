#!/usr/bin/env python3
"""Ensure correct received bits alone cannot pass electrical margin qualification."""
import tempfile
import unittest
from pathlib import Path

from receiver_margins import measure


class ReceiverMarginTests(unittest.TestCase):
    def run_trace(self, values, received=((250000, 1),), step=25, budget=100):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.txt'
            trace.write_text('time data clock\n' + '\n'.join(f'{t * 1e-9} {v} 0' for t, v in values) + '\n')
            return measure(trace, received, step, budget)

    def test_stable_interval_and_censored_ends(self):
        result = self.run_trace([(t, 0) for t in range(0, 501, 25)])
        self.assertTrue(result['withinBudget'])
        self.assertAlmostEqual(result['minimumSampledSetupNs'], 250)
        self.assertAlmostEqual(result['minimumSampledHoldNs'], 250)
        self.assertTrue(result['events'][0]['leftCensored'])
        self.assertTrue(result['events'][0]['rightCensored'])

    def test_unknown_voltage_near_edge_breaks_margin(self):
        for bad_time in (200, 300):
            with self.subTest(bad_time=bad_time):
                result = self.run_trace([(t, 1.4 if t == bad_time else 0) for t in range(0, 501, 25)])
                self.assertFalse(result['withinBudget'])

    def test_wrong_data_missing_samples_and_missing_activity_rejected(self):
        cases = [([(t, 5) for t in range(0, 501, 25)], ((250000, 1),)),
                 ([(0, 0), (500, 0)], ((250000, 1),)),
                 ([(t, 0) for t in range(0, 501, 25)], ())]
        for values, received in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.run_trace(values, received)

    def test_valid_high_wire_is_logical_zero(self):
        result = self.run_trace([(t, 5) for t in range(0, 501, 25)], ((250000, 0),))
        self.assertTrue(result['withinBudget'])


if __name__ == '__main__':
    unittest.main()
