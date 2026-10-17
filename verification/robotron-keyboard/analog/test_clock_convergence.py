#!/usr/bin/env python3
"""Identical bits or average frequency cannot conceal electrical clock phase drift."""
import tempfile
import unittest
from pathlib import Path

from clock_convergence import compare_clocks


class ClockConvergenceTests(unittest.TestCase):
    def compare(self, period=100, shift=0, amplitude=5, fine_step=5, gap=False, tolerance=15):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('coarse.txt', 'fine.txt')]
            for path, step, cycle, offset, high in [(paths[0], 10, 100, 0, 5),
                                                    (paths[1], fine_step, period, shift, amplitude)]:
                rows = []
                for t in range(0, 1001, step):
                    if gap and path == paths[1] and t == 105:
                        continue
                    voltage = high if (t - offset) % cycle >= cycle / 2 else 0
                    rows.append(f'{t * 1e-9} {voltage} 5 0 0')
                path.write_text('time clock reset data serial_clock\n' + '\n'.join(rows))
            return compare_clocks(paths[0], paths[1], 10, 5, tolerance)

    def test_matching_clock_with_sample_uncertainty(self):
        result = self.compare()
        self.assertTrue(result['passed'])
        self.assertEqual(result['waveforms']['coarse']['edges'], 20)
        self.assertAlmostEqual(result['waveforms']['coarse']['meanPeriodNs'], 100)

    def test_phase_shift_is_not_realigned(self):
        result = self.compare(shift=20)
        self.assertFalse(result['passed'])
        self.assertIsNotNone(result['firstDifference'])

    def test_accumulated_drift_is_not_hidden_by_short_period(self):
        result = self.compare(period=102)
        self.assertFalse(result['passed'])

    def test_brackets_prevent_false_precision(self):
        result = self.compare(tolerance=2)
        self.assertFalse(result['passed'])
        self.assertGreater(result['maximumBracketDifferenceNs'], 2)

    def test_voltage_change_fails_even_with_same_edge_order(self):
        result = self.compare(amplitude=4)
        self.assertFalse(result['passed'])
        self.assertEqual(result['sampledExtremaDifferencesVolts']['maximumVolts'], 1)

    def test_missing_samples_rejected(self):
        with self.assertRaisesRegex(ValueError, 'timestep'):
            self.compare(gap=True)


if __name__ == '__main__':
    unittest.main()
