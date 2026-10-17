#!/usr/bin/env python3
"""A failed run must not lose its evidence or acquire an earlier run's waveform."""
import gzip
import hashlib
import tempfile
import unittest
from pathlib import Path
from failure_evidence import capture


class FailureEvidenceTests(unittest.TestCase):
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
