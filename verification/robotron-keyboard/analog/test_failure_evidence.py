#!/usr/bin/env python3
"""A failed run must not lose its evidence or acquire an earlier run's waveform."""
import gzip
import hashlib
import tempfile
import unittest
from pathlib import Path
from failure_evidence import capture, solver_diagnostic


class FailureEvidenceTests(unittest.TestCase):
    def test_structured_startup_error_audit_is_not_failure(self):
        keys = ('time state delta dt0 dt1 dt2 order before proposed currenttol '
                'chargetol abstol reltol chgtol difference q0 q1 q2 q3').split()
        record = 'STARTUP_TRUNC error ' + ' '.join(k+'='+('2' if k in ('state','order') else '0x1.2p-3') for k in keys)
        self.assertIsNone(solver_diagnostic(record))
        for line in (record+' fatal', record.replace('q3=', 'missing='), 'WARNING: '+record):
            self.assertEqual(solver_diagnostic(line), line)
        self.assertEqual(solver_diagnostic(record+'\nTimestep too small'), 'Timestep too small')

    def test_unlabelled_solver_diagnostics_are_not_passes(self):
        message = 'Instance: ahdl   Message: XSPICE time is behind vtime:'
        log = message + '\nXSPICE 0.043\nCosim  0.043\nngspice-47 done\n'
        self.assertEqual(solver_diagnostic(log), message)
        for message in ('tran simulation(s) aborted', 'Timestep too small',
                        'WARNING: output scheduled with impossible delay', 'FATAL error'):
            with self.subTest(message=message):
                self.assertEqual(solver_diagnostic(message), message)
        self.assertIsNone(solver_diagnostic('No. of Data Rows : 100\nngspice-47 done\n'))

    def test_options_heading_does_not_hide_real_errors(self):
        for kind in ('charge', 'voltage'):
            heading = f'Truncation error correction, {kind} based, is selected:'
            self.assertIsNone(solver_diagnostic(heading))
            self.assertEqual(solver_diagnostic(heading+'\nTimestep too small'), 'Timestep too small')
            self.assertEqual(solver_diagnostic('WARNING: '+heading), 'WARNING: '+heading)
            self.assertEqual(solver_diagnostic(heading+' failed'), heading+' failed')

    def test_partial_output_is_retained_without_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            content = b'time voltage\n0 0\n1e-9 NaN\n2e-9 '
            (directory / 'trace.txt').write_bytes(content)
            report = capture(directory, ('trace.txt', 'ngspice.log'))
            self.assertEqual(report['trace.txt'], {'status': 'retained', 'bytes': len(content),
                             'sha256': hashlib.sha256(content).hexdigest()})
            self.assertEqual(report['ngspice.log'], {'status': 'missing'})
            self.assertEqual((directory / 'trace.txt').read_bytes(), content)

    def test_stale_compression_and_unreadable_output_do_not_mask_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with gzip.open(directory / 'trace.txt.gz', 'wb') as stream:
                stream.write(b'old run')
            (directory / 'ngspice.log').mkdir()
            report = capture(directory, ('trace.txt', 'ngspice.log'))
            self.assertEqual(report['trace.txt'], {'status': 'missing'})
            self.assertEqual(report['ngspice.log']['status'], 'unreadable')


if __name__ == '__main__':
    unittest.main()
