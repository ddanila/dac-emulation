#!/usr/bin/env python3
import gzip
import hashlib
import json
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
            subprocess.run([sys.executable, str(HERE / 'compress_trace.py'), str(root)], check=True, capture_output=True)
            self.assertFalse(trace.exists())
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

    def test_corrupt_compressed_data_cannot_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.txt'
            (Path(str(trace) + '.gz')).write_bytes(gzip.compress(b'evidence')[:-5])
            with self.assertRaises(EOFError):
                sha(trace)


if __name__ == '__main__':
    unittest.main()
