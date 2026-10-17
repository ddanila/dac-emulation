#!/usr/bin/env python3
import gzip
import hashlib
import json
import lzma
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trace_io import open_text
from compare_firmware_io import sha

HERE = Path(__file__).resolve().parent


class TraceStorageTests(unittest.TestCase):
    def test_compaction_preserves_hash_and_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / 'trace.txt'
            data = b'time voltage\n0 5\n' * 1000
            trace.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            (root / 'report.json').write_text(json.dumps({'passed': True, 'traceSha256': digest}))
            subprocess.run([sys.executable, str(HERE / 'compress_trace.py'), '--format', 'gzip', str(root)], check=True, capture_output=True)
            self.assertFalse(trace.exists())
            self.assertEqual(sha(trace), digest)
            with open_text(trace) as stream:
                self.assertEqual(stream.read(), data.decode())

    def test_gzip_to_xz_keeps_logical_hash_without_raw_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / 'trace.txt'
            data = b'time voltage\n0 5\n' * 1000
            digest = hashlib.sha256(data).hexdigest()
            (root / 'trace.txt.gz').write_bytes(gzip.compress(data))
            (root / 'report.json').write_text(json.dumps({'passed': True, 'traceSha256': digest}))
            subprocess.run([sys.executable, str(HERE / 'compress_trace.py'), '--format', 'xz', str(root)], check=True, capture_output=True)
            self.assertFalse(trace.exists())
            self.assertFalse((root / 'trace.txt.gz').exists())
            self.assertEqual(lzma.decompress((root / 'trace.txt.xz').read_bytes()), data)
            self.assertEqual(sha(trace), digest)
            with open_text(trace) as stream:
                self.assertEqual(stream.read(), data.decode())

    def test_failed_or_changed_run_is_preserved(self):
        for passed, digest in [(False, 'bad'), (True, 'bad')]:
            with self.subTest(passed=passed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                trace = root / 'trace.txt'
                trace.write_bytes(b'evidence')
                (root / 'report.json').write_text(json.dumps({'passed': passed, 'traceSha256': digest}))
                result = subprocess.run([sys.executable, str(HERE / 'compress_trace.py'), str(root)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(trace.read_bytes(), b'evidence')
                self.assertFalse((root / 'trace.txt.gz').exists())

    def test_completed_clock_probe_compacts_both_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b'time voltage\n0 5\n' * 1000
            digest = hashlib.sha256(data).hexdigest()
            for name in ('trace.txt', 'diagnostic-trace.txt'):
                (root / name).write_bytes(data)
            # Prepared boot is not a completed run; early clock execution is.
            (root / 'report.json').write_text(json.dumps({'passed': False, 'preparedOnly': True}))
            report = {'completed': True, 'traceSha256': digest, 'diagnosticTraceSha256': digest}
            (root / 'clock-probe.json').write_text(json.dumps(report))
            subprocess.run([sys.executable, str(HERE / 'compress_trace.py'), '--clock-probe', str(root)],
                           check=True, capture_output=True)
            for name in ('trace.txt', 'diagnostic-trace.txt'):
                self.assertFalse((root / name).exists())
                self.assertEqual(sha(root / name), digest)
                self.assertEqual(lzma.decompress((root / (name+'.xz')).read_bytes()), data)

    def test_clock_probe_rejects_incomplete_or_failed_reports(self):
        digest = hashlib.sha256(b'evidence').hexdigest()
        valid = {'completed': True, 'traceSha256': digest, 'diagnosticTraceSha256': digest}
        reports = [dict(valid, completed=False), dict(valid, error='timeout'),
                   dict(valid, solverDiagnostic='aborted'),
                   {'completed': True, 'traceSha256': digest}]
        for report in reports:
            with self.subTest(report=report), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'trace.txt').write_bytes(b'evidence')
                (root / 'clock-probe.json').write_text(json.dumps(report))
                result = subprocess.run([sys.executable, str(HERE / 'compress_trace.py'),
                                         '--clock-probe', str(root)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / 'trace.txt').read_bytes(), b'evidence')
                self.assertFalse((root / 'trace.txt.xz').exists())

    def test_corrupt_compressed_data_cannot_hash(self):
        for suffix, compress in (('.gz', gzip.compress), ('.xz', lzma.compress)):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                trace = Path(directory) / 'trace.txt'
                Path(str(trace) + suffix).write_bytes(compress(b'evidence')[:-5])
                with self.assertRaises((EOFError, lzma.LZMAError)):
                    sha(trace)


if __name__ == '__main__':
    unittest.main()
