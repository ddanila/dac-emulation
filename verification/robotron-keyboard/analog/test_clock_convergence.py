#!/usr/bin/env python3
"""Identical bits or average frequency cannot conceal electrical clock phase drift."""
import tempfile
import unittest
from pathlib import Path

from clock_convergence import compare_clocks, crossings


class ClockConvergenceTests(unittest.TestCase):
    def compare(self, period=100, shift=0, amplitude=5, fine_step=5, gap=False, tolerance=15, columns=5):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('coarse.txt', 'fine.txt')]
            for path, step, cycle, offset, high in [(paths[0], 10, 100, 0, 5),
                                                    (paths[1], fine_step, period, shift, amplitude)]:
                rows = []
                for t in range(0, 1001, step):
                    if gap and path == paths[1] and t == 105:
                        continue
                    voltage = high if t >= offset and (t - offset) % cycle >= cycle / 2 else 0
                    rows.append(f'{t * 1e-9:.17e} {voltage} 5 0 0' + (' 0' if columns == 6 else ''))
                path.write_text('time clock reset data serial_clock\n' + '\n'.join(rows))
            return compare_clocks(paths[0], paths[1], 10, 5, tolerance, columns=columns)

    def test_matching_clock_with_sample_uncertainty(self):
        result = self.compare()
        self.assertTrue(result['passed'])
        self.assertEqual(result['waveforms']['coarse']['edges'], 20)
        self.assertAlmostEqual(result['waveforms']['coarse']['meanPeriodNs'], 100)

    def test_standalone_internal_nodes_do_not_change_clock_selection(self):
        self.assertTrue(self.compare(columns=6)['passed'])
        self.assertFalse(self.compare(columns=6, shift=20)['passed'])

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

    def test_constant_offset_is_separate_from_phase_change(self):
        result = self.compare(shift=20)
        self.assertFalse(result['passed'])
        for name, direction in result['phaseEvolution']['byDirection'].items():
            self.assertEqual(direction['matchedEdges'], 10 if name == 'rise' else 9)
            self.assertGreater(direction['first']['signedDifferenceNs'], 15)
            self.assertAlmostEqual(direction['lastMinusFirstNs'], 0)
            self.assertAlmostEqual(direction['rangeNs'], 0)

    def test_phase_evolution_preserves_drift_and_edge_direction(self):
        result = self.compare(period=102)
        evolution = result['phaseEvolution']['byDirection']
        self.assertEqual(set(evolution), {'rise', 'fall'})
        for direction in evolution.values():
            self.assertGreater(direction['lastMinusFirstNs'], 10)
            self.assertGreater(direction['rangeNs'], 10)
            self.assertGreater(direction['last']['edgeOrdinal'], direction['first']['edgeOrdinal'])
            self.assertGreaterEqual(direction['maximum']['signedDifferenceNs'],
                                    direction['last']['signedDifferenceNs'])

    def test_missing_samples_rejected(self):
        with self.assertRaisesRegex(ValueError, 'timestep'):
            self.compare(gap=True)


    def test_subnanosecond_missing_sample_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock.txt'
            path.write_text('time clock\n0 0\n1.25000000000000000e-10 5\n')
            with self.assertRaisesRegex(ValueError, 'timestep'):
                list(crossings(path, .0625, {}, columns=2))

    def test_printed_rounding_expands_edge_brackets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clock.txt'
            path.write_text('time clock\n1.00000e-3 0\n1.00001e-3 5\n'
                            '1.00002e-3 0\n1.00003e-3 5\n')
            stats = {}
            edges = list(crossings(path, 10, stats, columns=2))
            self.assertAlmostEqual(stats['maximumTimestampUncertaintyNs'], 5)
            self.assertLess(edges[0]['earliestSeconds'], edges[0]['beforeSeconds'])
            self.assertGreater(edges[0]['latestSeconds'], edges[0]['afterSeconds'])
            result = compare_clocks(path, path, 10, 10, tolerance_ns=15, columns=2)
            self.assertFalse(result['passed'])
            self.assertAlmostEqual(result['maximumBracketDifferenceNs'], 20)


if __name__ == '__main__':
    unittest.main()
