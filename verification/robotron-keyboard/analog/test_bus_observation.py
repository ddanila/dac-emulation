#!/usr/bin/env python3
"""Reject missing, uncertain or electrically inconsistent CPU bus observations."""
from pathlib import Path
import tempfile
import unittest

from bus_observation import measure, BusMismatch
from test_raw_pair_review import write as write_raw

LOG = ('BUS_SAMPLE 100000 0001 a5 0 1 0\nBUS_LATCH 150000 a5 a5\n'
       'BUS_SAMPLE 300000 8000 a5 1 0 1\nBUS_LATCH 350000 a5 a5\n')
HEADER = 'time ' + ' '.join(f'v(n_D{i})' for i in range(8)) + ' v(n_p5V)\n'


class BusObservationTests(unittest.TestCase):
    def test_raw_samples_preserve_text_bus_assessment_and_reject_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace=Path(temporary)/'bus.raw'
            write_raw(trace,self.rows,HEADER.split())
            result=measure(LOG,trace,10,bytes([0xa5])*2048,setup_ns=20,hold_ns=10,raw_count=len(self.rows))
            self.assertEqual(result,self.check())
            original=trace.read_bytes()
            for data in (original[:-1],original+b'x'):
                trace.write_bytes(data)
                with self.assertRaises(ValueError):
                    measure(LOG,trace,10,raw_count=len(self.rows))
            bad=[r[:] for r in self.rows];bad[10][1]=1.4
            write_raw(trace,bad,HEADER.split())
            with self.assertRaisesRegex(BusMismatch,'D0'):
                measure(LOG,trace,10,raw_count=len(bad))

    def setUp(self):
        self.rows = [[i * 1e-9, *[4.5 if 0xa5 & (1 << bit) else .2 for bit in range(8)], 5]
                     for i in range(0, 401, 10)]

    def check(self, log=LOG, rows=None, header=HEADER, rom=bytes([0xa5]) * 2048, trace_extent=None, start_tolerance_ns=0):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / 'trace.txt'
            trace.write_text(header + ''.join(' '.join(map(str, row)) + '\n'
                                             for row in (self.rows if rows is None else rows)))
            return measure(log, trace, 10, rom, setup_ns=20, hold_ns=10, trace_extent=trace_extent, start_tolerance_ns=start_tolerance_ns)

    def test_memory_io_and_latch_agree_with_bracketed_voltages(self):
        report = self.check()
        self.assertEqual(report['sampleCount'], 2)
        self.assertEqual(report['memoryReads'], 1)
        self.assertEqual(report['ioReads'], 1)
        self.assertAlmostEqual(report['minimumLowMarginVolts'], .6)
        self.assertEqual(report['minimumHighMarginVolts'], 2.5)
        self.assertFalse(report['qualified'])

    def test_driver_states_preserve_release_and_unknown_on_failure(self):
        drives = ('BUS_DRIVE 100000 ' + '0'*24 + ' ' + '0'*24 + '\n' +
                  'BUS_DRIVE 300000 ' + '0'*16 + 'x0000000 ' + '0'*24 + '\n')
        with self.assertRaises(BusMismatch) as caught:
            self.check(log=LOG.replace('8000 a5', '8000 aX') + drives)
        owners = caught.exception.details['drivers']
        self.assertEqual(owners['cpu']['lowEnableBits7To0'], 'x0000000')
        self.assertEqual(owners['rom']['lowEnableBits7To0'], '00000000')
        self.assertEqual(owners['latch']['highEnableBits7To0'], '00000000')
        self.assertEqual(caught.exception.details['signal'], 'CPU_DI_UNKNOWN')
        self.assertTrue(self.check(log=LOG + drives)['driverStatesCaptured'])
        for broken in (drives.replace('300000', '300001'), drives.splitlines()[0] + '\n'):
            with self.assertRaisesRegex(ValueError, 'driver observations'):
                self.check(log=LOG + broken)

    def test_postponed_region_latch_at_sampling_time(self):
        log = LOG.replace('150000', '100000').replace('350000', '300000')
        self.assertEqual(self.check(log=log)['sampleCount'], 2)
        with self.assertRaisesRegex(ValueError, 'CPU input register'):
            self.check(log=log.replace('BUS_LATCH 300000 a5 a5', 'BUS_LATCH 300000 a5 00'))
        with self.assertRaisesRegex(ValueError, 'Missing bus'):
            self.check(log=log.replace('BUS_LATCH 300000 a5 a5\n', ''))

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

    def test_small_overrail_is_still_rejected_but_not_labelled_maximum_rating_failure(self):
        rows = [r[:] for r in self.rows]
        rows[10][1] = 5.000002
        with self.assertRaises(BusMismatch) as caught:
            self.check(rows=rows)
        classification = caught.exception.details['voltageClassification']
        self.assertFalse(classification['staticInputRangePassed'])
        self.assertTrue(classification['withinAbsoluteInputRatings'])
        self.assertTrue(classification['logicThresholdPassed'])

    def test_first_read_electrical_failure_precedes_later_rom_mismatch(self):
        log = LOG.replace('8000 a5 1 0 1', '0002 a4 0 1 0').replace('350000 a5 a5', '350000 a4 a4')
        rows = [r[:] for r in self.rows]
        rows[10][1] = 1.4
        with self.assertRaises(BusMismatch) as caught:
            self.check(log=log, rows=rows)
        details = caught.exception.details
        self.assertEqual(details['ordinal'], 0)
        self.assertEqual(details['readTimePs'], 100000)
        self.assertEqual(details['address'], 1)
        self.assertEqual(details['signal'], 'D0')
        self.assertEqual(details['expectedBit'], 1)
        self.assertEqual(details['volts'], 1.4)

    def test_unknown_data_is_rejected_in_read_order_with_raw_context(self):
        for field in ('sample', 'recorded', 'latched'):
            for raw in ('4X', 'xz', 'Z5'):
                log = LOG
                if field == 'sample':
                    log = log.replace('8000 a5', f'8000 {raw}')
                elif field == 'recorded':
                    log = log.replace('350000 a5 a5', f'350000 {raw} a5')
                else:
                    log = log.replace('350000 a5 a5', f'350000 a5 {raw}')
                with self.subTest(field=field, raw=raw):
                    with self.assertRaises(BusMismatch) as caught:
                        self.check(log=log)
                    details = caught.exception.details
                    self.assertEqual(details['ordinal'], 1)
                    self.assertEqual(details['signal'], 'CPU_DI_UNKNOWN')
                    self.assertEqual(details['address'], 0x8000)
                    self.assertEqual(details['readTimePs'], 300000)
                    self.assertEqual(details['ioSelectN'], 0)
                    self.assertEqual(details[{'sample': 'sampledHex',
                                             'recorded': 'recordedSampleHex',
                                             'latched': 'latchedHex'}[field]], raw)
                    rows = [r[:] for r in self.rows]
                    rows[10][1] = 1.4
                    with self.assertRaises(BusMismatch) as earlier:
                        self.check(log=log, rows=rows)
                    self.assertEqual(earlier.exception.details['ordinal'], 0)
                    self.assertEqual(earlier.exception.details['signal'], 'D0')

    def test_four_state_parser_still_rejects_malformed_data(self):
        for raw in ('gg', 'a', 'xxx', '??'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'malformed'):
                self.check(log=LOG.replace('8000 a5', f'8000 {raw}'))
        self.assertTrue(self.check(log=LOG.replace('a5', 'A5'))['passed'])

    def test_rom_and_cpu_register_failures_retain_expected_and_actual_data(self):
        with self.assertRaises(BusMismatch) as caught:
            self.check(rom=bytes(2048))
        self.assertEqual(caught.exception.details['signal'], 'ROM_DATA')
        self.assertEqual(caught.exception.details['expectedByte'], 0)
        self.assertEqual(caught.exception.details['sampledByte'], 0xa5)
        with self.assertRaises(BusMismatch) as caught:
            self.check(log=LOG.replace('150000 a5 a5', '150000 a5 00'))
        self.assertEqual(caught.exception.details['signal'], 'CPU_DI_REG')
        self.assertEqual(caught.exception.details['latchedByte'], 0)
        self.assertEqual(caught.exception.details['latchTimePs'], 150000)

    def test_explicit_tail_capture_start_allowance(self):
        rows = [list(row) for row in self.rows]
        rows[0][0] = .15e-9
        with self.assertRaisesRegex(ValueError, 'capture extent'):
            self.check(rows=rows, trace_extent=(0, 400e-9))
        result = self.check(rows=rows, trace_extent=(0, 400e-9), start_tolerance_ns=10)
        self.assertEqual(result['waveform']['startOffsetSeconds'], .15e-9)
        for shortened in (rows[2:], rows[:-1]):
            with self.assertRaisesRegex(ValueError, 'capture extent'):
                self.check(rows=shortened, trace_extent=(0, 400e-9), start_tolerance_ns=10)
        for tolerance in (-1, 11, float('nan')):
            with self.assertRaisesRegex(ValueError, 'start tolerance'):
                self.check(trace_extent=(0, 400e-9), start_tolerance_ns=tolerance)

    def test_reads_alone_do_not_prove_complete_capture(self):
        self.assertEqual(self.check(trace_extent=(0, 400e-9))['waveform']['rows'], 41)
        # Both shortened captures still contain every read window.
        for rows in (self.rows[1:], self.rows[:-1]):
            self.assertTrue(self.check(rows=rows)['passed'])
            with self.assertRaisesRegex(ValueError, 'capture extent'):
                self.check(rows=rows, trace_extent=(0, 400e-9))
        for extent in ((0, 0), (-1, 1), (0, float('inf')), (0,)):
            with self.assertRaisesRegex(ValueError, 'expected bus capture extent'):
                self.check(trace_extent=extent)


if __name__ == '__main__':
    unittest.main()
