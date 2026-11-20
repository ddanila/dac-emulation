"""Streaming hashes work on Python versions without hashlib.file_digest."""
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import file_hash


class LimitedRead(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.reads = 0

    def read(self, size=-1):
        if size <= 0 or size > 1024 * 1024:
            raise AssertionError('hash must read bounded chunks')
        self.reads += 1
        return super().read(size)


class FileHashTests(unittest.TestCase):
    def test_large_artifact_matches_sha256_with_bounded_reads(self):
        value = bytes(range(256)) * 12000
        stream = LimitedRead(value)
        expected = hashlib.sha256(value).hexdigest()
        self.assertEqual(file_hash.digest_stream(stream), expected)
        self.assertGreater(stream.reads, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'artifact.raw'
            path.write_bytes(value)
            self.assertEqual(file_hash.digest(path), expected)


if __name__ == '__main__':
    unittest.main()
