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

    def test_global_extrema_cannot_hide_one_bad_cycle(self):
        result = self.check_samples([(v, 5) for v in (.2, 4.9, .2, 3.6, .2, 4.9)])
        self.assertTrue(result['bothExcursionsObserved'])
        self.assertEqual(result['cycles']['assessedWithinSupplyRange'], 2)
        self.assertEqual(result['cycles']['missingHighExcursion'], 1)
        self.assertEqual(result['cycles']['firstFailure']['cycleOrdinal'], 1)

    def test_incomplete_and_unpowered_cycles_do_not_count(self):
        result = self.check_samples([(v, 5) for v in (4.9, .2, 4.9)])
        self.assertEqual(result['cycles']['assessedWithinSupplyRange'], 0)
        result = self.check_samples([(.2, 5), (4.9, 5), (.2, 4), (4.9, 5)])
        self.assertEqual(result['cycles']['assessedWithinSupplyRange'], 0)
        self.assertEqual(result['cycles']['excludedForSupply'], 1)

    def test_low_level_failure_and_valid_cycles(self):
        result = self.check_samples([(v, 5) for v in (.2, 4.9, 1.0, 4.9)])
        self.assertEqual(result['cycles']['missingLowExcursion'], 1)
        result = self.check_samples([(v, 5) for v in (.2, 4.9, .2, 4.9, .2, 4.9)])
        self.assertEqual(result['cycles']['assessedWithinSupplyRange'], 2)
        self.assertIsNone(result['cycles']['firstFailure'])

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

    def test_supply_only_capture_matches_diagnostic_capture(self):
        import lzma
        with tempfile.TemporaryDirectory() as directory:
            p, d, s = (Path(directory) / name for name in ('clock', 'diagnostic', 'supply'))
            p.write_text('time clock reset data serial\n0 .2 0 0 0\n1 4.9 0 0 0\n')
            d.write_text('time supply rc osc1 osc2 out ground current\n0 5 0 0 0 0 0 0\n1 5 0 0 0 0 0 0\n')
            Path(str(s) + '.xz').write_bytes(lzma.compress(b'time supply\n0 5\n1 5\n'))
            self.assertEqual(inspect(p, d), inspect(p, s, diagnostic_columns=2))
            with self.assertRaises(ValueError):
                inspect(p, s)


if __name__ == '__main__':
    unittest.main()
