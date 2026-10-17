#!/usr/bin/env python3
"""Reject misleading timestep comparisons and corrupted retained inputs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from compare_firmware_io import compare, load_run, sha
from serial_observation import validate_transport


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

    def test_receiver_shift_fails_even_with_same_bits(self):
        result = compare(self.coarse, self.fine, self.tx, self.rx, 15)
        self.assertEqual(result['transmittedMaximumDifferenceNs'], 0)
        self.assertEqual(result['receivedMaximumDifferenceNs'], 20)
        self.assertFalse(result['withinTolerance'])
        self.assertTrue(compare(self.coarse, self.fine, self.tx, self.tx, 15)['withinTolerance'])

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
