import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from postreset_retention_benchmark import HERE
from ttl7406_probe import sha


class ArchiveProducerTests(unittest.TestCase):
    def execute(self,root,mutation=None):
        raw=b'complete retained bytes\x00\xff';log=b'No. of Data Rows : 3\n'
        (root/'waveform.raw.xz').write_bytes(lzma.compress(raw))
        (root/'ngspice.log.xz').write_bytes(lzma.compress(log))
        def receipt(data):return dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        (root/'run.json').write_text(json.dumps(dict(storage={'waveform.raw':receipt(raw)},log=receipt(log))))
        digest=sha(root/'run.json')
        if mutation=='raw':(root/'waveform.raw.xz').write_bytes(lzma.compress(raw+b'changed'))
        if mutation=='log':(root/'ngspice.log.xz').write_bytes(lzma.compress(log+b'changed'))
        if mutation=='receipt':(root/'run.json').write_text('{}')
        with (root/'received.raw').open('wb') as target:
            result=subprocess.run([sys.executable,str(HERE/'postreset_retention_benchmark.py'),
                '--worker',str(root),'--fd',str(target.fileno()),'--receipt-hash',digest],
                pass_fds=(target.fileno(),),capture_output=True,timeout=5)
        return result,(root/'received.raw').read_bytes(),raw,log

    def test_worker_preserves_raw_and_authentic_completion_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,received,raw,log=self.execute(Path(tmp))
            self.assertEqual(result.returncode,0)
            self.assertEqual(received,raw)
            self.assertEqual(result.stdout,log)

    def test_worker_refuses_changed_source_receipt_or_bytes(self):
        for mutation in ('raw','log','receipt'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                result,_,_,_=self.execute(Path(tmp),mutation)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(b'Changed',result.stderr)


if __name__=='__main__':unittest.main()
