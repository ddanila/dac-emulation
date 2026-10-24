import hashlib
import lzma
import os
from pathlib import Path
import sys
import tempfile
import unittest
from live_capture import run


class LiveCaptureTests(unittest.TestCase):
    def execute(self, root, script, timeout=10, compressed=True):
        with (root / 'log').open('w') as log:
            return run([sys.executable, '-c', script], root, os.environ.copy(), log,
                       timeout, 'wrdata one.txt v(a)\nwrdata two.txt v(b)\n',
                       compressed=compressed)

    def test_raw_and_compressed_producer_bytes_match(self):
        script = "from pathlib import Path; " + '; '.join(
            "Path(%r).write_bytes(%r)" % (name, data)
            for name, data in [('one.txt', b'time a\n0 0\n1 5\n'),
                               ('two.txt', b'time b\n0 5\n1 0\n')])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw, zipped = root/'raw', root/'zipped'
            raw.mkdir(); zipped.mkdir()
            self.assertEqual(self.execute(raw, script, compressed=False), (0, False, None, {}))
            code, timeout, error, records = self.execute(zipped, script)
            self.assertEqual((code, timeout, error), (0, False, None))
            for name in ('one.txt', 'two.txt'):
                expected = (raw/name).read_bytes()
                self.assertEqual(lzma.decompress((zipped/(name+'.xz')).read_bytes()), expected)
                self.assertEqual(records[name], dict(bytes=len(expected), sha256=hashlib.sha256(expected).hexdigest()))

    def test_timeout_and_failure_do_not_wait_on_unopened_fifos(self):
        for script, timeout, expected in [('import time; time.sleep(30)', .1, (None, True)),
                                           ('raise SystemExit(7)', 10, (7, False))]:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                code, timed_out, error, records = self.execute(root, script, timeout)
                self.assertEqual((code, timed_out), expected)
                self.assertIsNone(error)
                self.assertEqual(records, {})
                self.assertFalse((root/'one.txt').exists())
                self.assertFalse((root/'one.txt.xz').exists())


if __name__ == '__main__':
    unittest.main()
