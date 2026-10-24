import hashlib
import lzma
import os
from pathlib import Path
import sys
import tempfile
import unittest
from live_capture import run


class LiveCaptureTests(unittest.TestCase):
    def test_direct_raw_stream_preserves_binary_bytes(self):
        data=bytes(range(256))*32
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with (root/'log').open('w') as log:
                code,timeout,error,records=run(
                    [sys.executable,'-c',f'from pathlib import Path; Path("waveform.raw").write_bytes({data!r})'],
                    root,os.environ.copy(),log,10,'set filetype=binary\nrun waveform.raw\n',compressed=True)
            self.assertEqual((code,timeout,error),(0,False,None))
            self.assertEqual(lzma.decompress((root/'waveform.raw.xz').read_bytes()),data)
            self.assertEqual(records['waveform.raw']['sha256'],hashlib.sha256(data).hexdigest())

    def test_rejects_mixed_or_uncompressed_raw_outputs(self):
        for deck,compressed in [('run waveform.raw\nwrdata a v(a)\n',True),
                                ('run waveform.raw\n',False),('run other.raw\n',True)]:
            with self.subTest(deck=deck),tempfile.TemporaryDirectory() as d:
                with (Path(d)/'log').open('w') as log,self.assertRaises(ValueError):
                    run([],Path(d),{},log,10,deck,compressed=compressed)

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
