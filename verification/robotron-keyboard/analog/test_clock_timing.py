#!/usr/bin/env python3
"""Clock-level excursions alone must not hide short pulses or slow transitions."""
import tempfile
from pathlib import Path
import unittest

from clock_timing import inspect


class ClockTimingTests(unittest.TestCase):
    def run_samples(self, samples, supply=5, step=250):
        with tempfile.TemporaryDirectory() as temporary:
            p, r = Path(temporary) / 'clock', Path(temporary) / 'supply'
            p.write_text('time clock reset data serial\n' + ''.join(
                f'{t * 1e-9:.17g} {v} 0 0 0\n' for t, v in samples))
            r.write_text('time supply\n' + ''.join(f'{t * 1e-9:.17g} {supply}\n' for t, _ in samples))
            return inspect(p, r, step, diagnostic_columns=2)

    def valid_samples(self):
        return [(0, 0), (10, 0), (20, 2.5), (25, 5), (230, 5), (235, 2.5),
                (240, 0), (440, 0), (445, 2.5), (450, 5), (655, 5),
                (660, 2.5), (665, 0), (865, 0), (870, 2.5), (875, 5)]

    def test_valid_sample_brackets(self):
        result = self.run_samples(self.valid_samples())
        self.assertTrue(result['passed'])
        self.assertFalse(result['qualified'])
        self.assertEqual(result['measurements']['high']['observations'], 2)

    def test_input_range_violation_cannot_pass_timing(self):
        samples = self.valid_samples() + [(900, 5.01)]
        result = self.run_samples(samples)
        self.assertEqual(result['inputRangeViolations'], 1)
        self.assertFalse(result['passed'])

    def test_short_high_and_fast_period_fail(self):
        result = self.run_samples([(t / 2, v) for t, v in self.valid_samples()])
        self.assertGreater(result['measurements']['high']['failed'], 0)
        self.assertGreater(result['measurements']['period']['failed'], 0)
        self.assertFalse(result['passed'])

    def test_slow_rise_and_incomplete_supply_evidence(self):
        result = self.run_samples([(0, 5), (10, 0), (20, 2.5), (80, 2.5), (90, 5)])
        self.assertEqual(result['measurements']['rise']['failed'], 1)
        result = self.run_samples(self.valid_samples(), supply=4)
        self.assertEqual(result['validSupplySamples'], 0)
        self.assertFalse(result['passed'])

    def test_aborted_excursion_and_censoring(self):
        result = self.run_samples([(0, 0), (10, 2.5), (20, 0), (30, 0)])
        self.assertEqual(result['abortedExcursions'], 1)
        self.assertEqual(result['measurements']['low']['observations'], 0)
        self.assertFalse(result['passed'])

    def test_sample_gap_and_nonfinite_rejected(self):
        for samples, step in [(self.valid_samples(), 1), ([(0, float('nan'))], 10), ([], 10)]:
            with self.assertRaises(ValueError):
                self.run_samples(samples, step=step)

    def test_boundary_uncertainty_is_not_a_pass(self):
        result = self.run_samples([(0, 0), (10, 2.5), (20, 5), (195, 5), (205, 2.5), (210, 0)])
        self.assertEqual(result['measurements']['high']['indeterminate'], 1)


if __name__ == '__main__':
    unittest.main()
