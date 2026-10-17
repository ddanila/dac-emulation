#!/usr/bin/env python3
"""Reject misleading timestep comparisons and corrupted retained inputs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from compare_firmware_io import compare, load_run, sha
from serial_observation import SerialMismatch, validate_transport


def report(step):
    return {'assumptions': {'stepNs': step, 'bridgeDelayNs': 10},
            **{key: 'same' for key in ('romSha256', 'connectivitySha256', 'bridge', 'tv80', 'ngspice', 'iverilog')},
            'sources': {name: 'same' for name in ('circuit.py', 'matrix.py', 'output_circuit.py',
                'controller_interface.py', 'boot_cosim.v', 'firmware_io_cosim.v', 'serial_observation.py')},
            'hdlSha256': {'/fixture/boot.v': 'same'}}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.coarse, self.fine = report(100), report(50)
        self.tx = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 21000 1\n', True)
        self.rx = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 41000 1\n', True)

    def test_retained_explicit_breakpoint_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            log = 'SERIAL_TX 1000 1\nSERIAL_RX 21000 1\n'
            deck = 'fixture\n.options minbreak=1f\n.tran 100n 30m\n.control\nrun\n.endc\n.end\n'
            (path / 'ngspice.log').write_text(log)
            (path / 'io.cir').write_text(deck)
            (path / 'trace.txt').write_text('retained fixture trace')
            r = {'passed': True, 'assumptions': {'stepNs': 100, 'minimumBreakpointFs': 1,
                 'analysisInvocation': 'deck-tran/run'}, 'deckSha256': sha(path / 'io.cir'),
                 'traceSha256': sha(path / 'trace.txt'), 'logSha256': sha(path / 'ngspice.log'),
                 'serialTransport': validate_transport(log, True)}
            (path / 'report.json').write_text(json.dumps(r))
            load_run(path)
            for invalid in (deck.replace('minbreak=1f', 'minbreak=2f'),
                            deck.replace('.tran 100n 30m', '').replace('run', 'tran 100n 30m'),
                            deck.replace('run', 'run\nrun')):
                (path / 'io.cir').write_text(invalid)
                r['deckSha256'] = sha(path / 'io.cir')
                (path / 'report.json').write_text(json.dumps(r))
                with self.assertRaisesRegex(ValueError, 'breakpoint'):
                    load_run(path)

    def test_code_model_change_rejected_with_same_version_string(self):
        self.coarse['ngspiceRuntime'] = {'codeModels': [{'sha256': 'baseline'}]}
        self.fine['ngspiceRuntime'] = copy.deepcopy(self.coarse['ngspiceRuntime'])
        self.assertTrue(compare(self.coarse, self.fine, self.tx, self.tx, 15)['withinTolerance'])
        self.fine['ngspiceRuntime']['codeModels'][0]['sha256'] = 'patched'
        with self.assertRaisesRegex(ValueError, 'code models differ'):
            compare(self.coarse, self.fine, self.tx, self.tx, 15)

    def test_control_interface_source_change_is_rejected(self):
        self.fine['sources']['logic_control.py'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Control interface source'):
            compare(self.coarse, self.fine, self.tx, self.tx, 15)

    def test_receiver_shift_fails_even_with_same_bits(self):
        result = compare(self.coarse, self.fine, self.tx, self.rx, 15)
        self.assertEqual(result['transmittedMaximumDifferenceNs'], 0)
        self.assertEqual(result['receivedMaximumDifferenceNs'], 20)
        self.assertFalse(result['withinTolerance'])
        self.assertEqual(result['firstTimingDifference']['signal'], 'serial_clock_RX')
        self.assertEqual(result['firstTimingDifference']['ordinal'], 0)
        self.assertEqual(result['firstTimingDifference']['coarseEventTimePs'], 21000)
        self.assertTrue(compare(self.coarse, self.fine, self.tx, self.tx, 15)['withinTolerance'])

    def test_transport_only_shift_and_exact_budget(self):
        coarse = validate_transport('SERIAL_TX 30000 1\nSERIAL_RX 60000 1\n', True)
        fine = validate_transport('SERIAL_TX 20000 1\nSERIAL_RX 70000 1\n', True)
        result = compare(self.coarse, self.fine, coarse, fine, 15)
        self.assertEqual(result['firstTimingDifference']['signal'], 'serial_clock_transport')
        self.assertEqual(result['transportMaximumDifferenceNs'], 20)
        result = compare(self.coarse, self.fine, coarse, fine, 20)
        self.assertTrue(result['withinTolerance'])
        self.assertIsNone(result['firstTimingDifference'])

    def test_first_timing_failure_is_earliest_not_largest_or_channel_order(self):
        coarse = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 21000 1\nSERIAL_TX 100000 0\nSERIAL_RX 120000 0\n', True)
        fine = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 41000 1\nSERIAL_TX 130000 0\nSERIAL_RX 160000 0\n', True)
        result = compare(self.coarse, self.fine, coarse, fine, 15)
        self.assertEqual(result['receivedMaximumDifferenceNs'], 40)
        self.assertEqual(result['firstTimingDifference']['signal'], 'serial_clock_RX')
        self.assertEqual(result['firstTimingDifference']['ordinal'], 0)
        self.assertEqual(result['firstTimingDifference']['differenceNs'], 20)

    def test_first_sequence_difference_retains_both_events(self):
        changed = validate_transport('SERIAL_TX 1000 0\nSERIAL_RX 21000 0\n', True)
        with self.assertRaises(SerialMismatch) as caught:
            compare(self.coarse, self.fine, self.tx, changed, 15)
        self.assertEqual(caught.exception.details['ordinal'], 0)
        self.assertEqual(caught.exception.details['coarse'], {'timePs': 1000, 'bit': 1})
        self.assertEqual(caught.exception.details['fine'], {'timePs': 1000, 'bit': 0})

    def test_different_models_or_unrefined_step_rejected(self):
        cases = []
        changed = copy.deepcopy(self.fine)
        changed['assumptions']['bridgeDelayNs'] = 20
        cases.append(changed)
        changed = copy.deepcopy(self.fine)
        changed['assumptions']['stepNs'] = 100
        cases.append(changed)
        changed = copy.deepcopy(self.fine)
        changed['sources']['matrix.py'] = 'changed'
        cases.append(changed)
        changed = copy.deepcopy(self.fine)
        changed['hdlSha256']['/fixture/boot.v'] = 'changed'
        cases.append(changed)
        for changed in cases:
            with self.subTest(report=changed), self.assertRaises(ValueError):
                compare(self.coarse, changed, self.tx, self.tx, 15)

    def test_latch_stress_requires_matching_limit_sources(self):
        for r in (self.coarse, self.fine):
            r['assumptions']['latchLoad'] = 'source-limit'
        with self.assertRaisesRegex(ValueError, 'Latch load source'):
            compare(self.coarse, self.fine, self.tx, self.tx, 15)
        for r in (self.coarse, self.fine):
            r['sources']['latch_limits.json'] = 'same'
        self.assertTrue(compare(self.coarse, self.fine, self.tx, self.tx, 15)['withinTolerance'])
        self.fine['sources']['latch_limits.json'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Latch load source'):
            compare(self.coarse, self.fine, self.tx, self.tx, 15)

    def test_corrupted_trace_and_misreported_timestep_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            log = 'SERIAL_TX 1000 1\nSERIAL_RX 21000 1\n'
            (path / 'ngspice.log').write_text(log)
            (path / 'io.cir').write_text('fixture\ntran 100n 30m\n.end\n')
            (path / 'trace.txt').write_text('retained fixture trace')
            r = {'passed': True, 'assumptions': {'stepNs': 100},
                 'deckSha256': sha(path / 'io.cir'), 'traceSha256': sha(path / 'trace.txt'),
                 'logSha256': sha(path / 'ngspice.log'), 'serialTransport': validate_transport(log, True)}
            (path / 'report.json').write_text(json.dumps(r))
            load_run(path)
            (path / 'ngspice.log').write_text(log + 'XSPICE time is behind vtime:\nXSPICE 0.043\nCosim 0.043\n')
            r['logSha256'] = sha(path / 'ngspice.log')
            (path / 'report.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError, 'Retained solver/HDL diagnostics'):
                load_run(path)
            (path / 'ngspice.log').write_text(log)
            r['logSha256'] = sha(path / 'ngspice.log')
            r['assumptions']['stepNs'] = 50
            (path / 'report.json').write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError, 'timestep'):
                load_run(path)
            r['assumptions']['stepNs'] = 100
            (path / 'report.json').write_text(json.dumps(r))
            (path / 'trace.txt').write_text('altered trace')
            with self.assertRaisesRegex(ValueError, 'hash'):
                load_run(path)

    def test_new_acceptance_windows_cannot_change_stimulus(self):
        self.coarse['assumptions']['scenario'] = {'cycles': 100, 'contacts': []}
        self.fine['assumptions']['scenario'] = {'cycles': 100, 'contacts': [], 'observations': ['new check']}
        self.assertTrue(compare(self.coarse, self.fine, self.tx, self.tx, 15)['withinTolerance'])
        self.fine['assumptions']['scenario']['contacts'] = [1]
        with self.assertRaisesRegex(ValueError, 'assumptions'):
            compare(self.coarse, self.fine, self.tx, self.tx, 15)


if __name__ == '__main__':
    unittest.main()
