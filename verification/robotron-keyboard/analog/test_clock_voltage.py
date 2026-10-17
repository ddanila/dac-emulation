#!/usr/bin/env python3
"""Reject logic-only clock evidence and mismatched retained rail samples."""
import tempfile
import unittest
from pathlib import Path

from clock_voltage import inspect


class ClockVoltageTests(unittest.TestCase):
    def check_samples(self, samples, rail_times=None):
        with tempfile.TemporaryDirectory() as directory:
            p, d = Path(directory) / 'clock', Path(directory) / 'rail'
            p.write_text('time clock reset data serial\n' + ''.join(
                f'{i} {clock} 0 0 0\n' for i, (clock, _) in enumerate(samples)))
            times = range(len(samples)) if rail_times is None else rail_times
            d.write_text('time supply rc osc1 osc2 out ground current\n' + ''.join(
                f'{i} {supply} 0 0 0 0 0 0\n' for i, (_, supply) in zip(times, samples)))
            return inspect(p, d)

    def test_ttl_high_does_not_meet_cpu_clock_high(self):
        result = self.check_samples([(0.2, 5), (3.6, 5)])
        self.assertTrue(result['lowExcursionObserved'])
        self.assertFalse(result['highExcursionObserved'])

    def test_pullup_excursions_are_not_qualification(self):
        result = self.check_samples([(0.2, 5), (4.9, 5)])
        self.assertTrue(result['bothExcursionsObserved'])
        self.assertFalse(result['qualified'])

    def test_startup_and_overvoltage_cannot_supply_evidence(self):
        result = self.check_samples([(0, 1), (1, 1), (0, 6), (6, 6)])
        self.assertEqual(result['validSupplySamples'], 0)
        self.assertIsNone(result['bestHighMarginVolts'])
        self.assertFalse(result['bothExcursionsObserved'])

    def test_misaligned_or_missing_samples_rejected(self):
        for times in ([0, 2], [0]):
            with self.assertRaises(ValueError):
                self.check_samples([(0.2, 5), (4.9, 5)], times)

    def test_nonfinite_and_empty_rejected(self):
        for samples in ([], [(float('nan'), 5)], [(0, float('inf'))]):
            with self.assertRaises(ValueError):
                self.check_samples(samples)


if __name__ == '__main__':
    unittest.main()
