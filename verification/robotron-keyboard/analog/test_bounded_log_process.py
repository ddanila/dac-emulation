import hashlib
import lzma
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from bounded_log_process import run


class BoundedLogTests(unittest.TestCase):
    def capture(self, code, root, **limits):
        return run([sys.executable, '-c', code], root, os.environ, root/'log.xz',
                   limits.pop('timeout', 5), logical_limit=limits.pop('logical_limit', 200000),
                   compressed_limit=limits.pop('compressed_limit', 200000))

    def test_complete_lossless_stream_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); payload=b'abc\n'*20000
            r=self.capture('import sys;sys.stdout.buffer.write(b"abc\\n"*20000);sys.exit(2)',root)
            self.assertEqual(r['exitCode'],2)
            self.assertEqual(r['bytes'],len(payload))
            self.assertEqual(r['sha256'],hashlib.sha256(payload).hexdigest())
            self.assertEqual(lzma.decompress((root/'log.xz').read_bytes()),payload)
            self.assertFalse((root/'log.xz.partial').exists())
            with self.assertRaises(ValueError): self.capture('print(1)',root)

    def test_log_budgets_fail_without_publishing_success(self):
        for limit in ('logical_limit','compressed_limit'):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaisesRegex(ValueError,'budget exceeded'):
                    self.capture('import os,sys;sys.stdout.buffer.write(os.urandom(100000));sys.stdout.flush()',root,**{limit:100})
                self.assertFalse((root/'log.xz').exists())
                self.assertLessEqual((root/'log.xz.partial').stat().st_size,100 if limit=='compressed_limit' else 200000)

    def test_timeout_stops_child_holding_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); start=time.monotonic()
            code='import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])'
            with self.assertRaises(TimeoutError): self.capture(code,root,timeout=.3)
            self.assertLess(time.monotonic()-start,5)
            self.assertFalse((root/'log.xz').exists())

    def test_free_space_reserve_stops_capture(self):
        for spaces in ([0], [1000, 0]):
            with self.subTest(spaces=spaces), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with patch('bounded_log_process.shutil.disk_usage',side_effect=[SimpleNamespace(free=n) for n in spaces]):
                    with self.assertRaisesRegex(OSError,'free-space reserve'):
                        run([sys.executable,'-c','import time;time.sleep(30)'],root,os.environ,root/'log.xz',5,
                            logical_limit=1000,compressed_limit=1000,min_free_bytes=100)
                self.assertFalse((root/'log.xz').exists())

    def test_invalid_budget_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            for options in ({'timeout':float('nan')},{'logical_limit':0},{'compressed_limit':True}):
                with self.assertRaises(ValueError): self.capture('print(1)',Path(tmp),**options)


if __name__=='__main__':unittest.main()
