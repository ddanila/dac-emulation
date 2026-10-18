#!/usr/bin/env python3
"""Reject missing, uncertain or electrically inconsistent CPU bus observations."""
from pathlib import Path
import tempfile
import unittest

from bus_observation import measure

LOG = ('BUS_SAMPLE 100000 0001 a5 0 1 0\nBUS_LATCH 150000 a5 a5\n'
       'BUS_SAMPLE 300000 8000 a5 1 0 1\nBUS_LATCH 350000 a5 a5\n')
HEADER = 'time ' + ' '.join(f'v(n_D{i})' for i in range(8)) + ' v(n_p5V)\n'


class BusObservationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [[i * 1e-9, *[4.5 if 0xa5 & (1 << bit) else .2 for bit in range(8)], 5]
                     for i in range(0, 401, 10)]

    def check(self, log=LOG, rows=None, header=HEADER, rom=bytes([0xa5]) * 2048):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / 'trace.txt'
            trace.write_text(header + ''.join(' '.join(map(str, row)) + '\n'
                                             for row in (self.rows if rows is None else rows)))
            return measure(log, trace, 10, rom, setup_ns=20, hold_ns=10)

    def test_memory_io_and_latch_agree_with_bracketed_voltages(self):
        report = self.check()
        self.assertEqual(report['sampleCount'], 2)
        self.assertEqual(report['memoryReads'], 1)
        self.assertEqual(report['ioReads'], 1)
        self.assertAlmostEqual(report['minimumLowMarginVolts'], .6)
        self.assertEqual(report['minimumHighMarginVolts'], 2.5)
        self.assertFalse(report['qualified'])

    def test_overlapping_read_windows_reuse_retained_samples(self):
        log = LOG.replace('150000', '105000').replace('300000', '110000').replace('350000', '115000')
        self.assertEqual(self.check(log=log)['sampleCount'], 2)
        rows = [r[:] for r in self.rows]
        rows[9][1] = 1.4
        with self.assertRaisesRegex(ValueError, 'D0'):
            self.check(log=log, rows=rows)

    def test_read_data_and_register_confirmation_are_not_optional(self):
        for log in (LOG.replace('0001 a5', '0001 ax'), LOG.replace('a5 a5', 'a5 00'),
                    LOG.replace('BUS_LATCH 150000 a5 a5\n', ''),
                    LOG.replace('150000', '90000'), LOG.replace('300000', '100000'),
                    LOG.replace('0 1 0', '0 0 0')):
            with self.subTest(log=log), self.assertRaises(ValueError):
                self.check(log=log)
        with self.assertRaisesRegex(ValueError, 'mapped ROM'):
            self.check(rom=bytes(2048))

    def test_unknown_band_or_wrong_pin_voltage_is_rejected(self):
        for value in (0, 1.4):
            rows = [r[:] for r in self.rows]
            rows[10][1] = value
            with self.assertRaisesRegex(ValueError, 'D0'):
                self.check(rows=rows)

    def test_missing_windows_gaps_and_invalid_tail_are_rejected(self):
        for rows in (self.rows[10:], self.rows[:31], self.rows[:10] + self.rows[12:],
                     self.rows + [[401e-9, *([float('nan')] * 9)]],
                     self.rows + [self.rows[0]]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.check(rows=rows)
        with self.assertRaisesRegex(ValueError, 'columns'):
            self.check(header=HEADER.replace('n_D0', 'n_D7'))

    def test_logic_agreement_does_not_hide_supply_or_input_range_failure(self):
        for column, value in ((9, 4.6), (9, 5.3), (1, 5.1), (2, -.6)):
            rows = [r[:] for r in self.rows]
            rows[10][column] = value
            with self.subTest(column=column, value=value), self.assertRaisesRegex(ValueError, 'range'):
                self.check(rows=rows)
        with self.assertRaisesRegex(ValueError, 'columns'):
            self.check(header=HEADER.replace(' v(n_p5V)', ''))


if __name__ == '__main__':
    unittest.main()
