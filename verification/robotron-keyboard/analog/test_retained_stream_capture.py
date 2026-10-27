import json
import lzma
import os
from pathlib import Path
import sys
import tempfile
import unittest

from retained_stream_capture import run
from retained_stream_review import replay
from stream_capture import run as unretained
from test_stream_capture import WORKER
from test_raw_pair_review import write


class RetainedStreamTests(unittest.TestCase):
    def commands(self,root,mode='ok',count=3):
        source=root/'source.raw'
        write(source,[(i/(count-1),i%2) for i in range(count)])
        return [lambda fd,i=i:([sys.executable,'-c',WORKER,str(fd),str(source),mode if i==1 else 'ok',str(count)],root) for i in range(3)]

    def capture(self,root,mode='ok',count=3,**limits):
        defaults=dict(max_raw_bytes=10**7,max_compressed_raw_bytes=10**6)
        defaults.update(limits)
        return run(self.commands(root,mode,count),root/'retained',os.environ.copy(),1,10,**defaults)

    def test_complete_lossless_replay_equals_unretained_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=self.capture(root,count=20001)
            baseline=unretained(self.commands(root,count=20001),root/'baseline',os.environ.copy(),1,10)
            self.assertEqual(result['comparisons'],baseline['comparisons'])
            self.assertEqual(result['streams'],baseline['streams'])
            self.assertEqual(replay(root/'retained')['streams'],result['streams'])
            for i in range(3):
                self.assertEqual(lzma.decompress((root/f'retained/{i}.raw.xz').read_bytes()),(root/'source.raw').read_bytes())
            self.assertFalse(list((root/'retained').glob('*.partial')))
            self.assertFalse(list((root/'retained').glob('*.raw')))

    def test_raw_caps_fail_without_success(self):
        for limits in ({'max_raw_bytes':100},{'max_compressed_raw_bytes':10}):
            with self.subTest(limits=limits),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises(ValueError):self.capture(root,**limits)
                self.assertFalse((root/'retained/transport.json').exists())
                self.assertFalse(list((root/'retained').glob('*.raw.xz')))
                failure=json.loads((root/'retained/failure.json').read_text())
                self.assertIn('budget',failure['detail'])
                if 'max_compressed_raw_bytes' in limits:
                    self.assertLessEqual(sum(p.stat().st_size for p in (root/'retained').glob('*.raw.xz.partial')),10)

    def test_invalid_or_omitted_raw_caps_refuse_before_launch(self):
        for value in (None,False,0,-1,1.5):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises(ValueError):self.capture(root,max_raw_bytes=value)
                self.assertFalse((root/'retained').exists())

    def test_late_failure_and_wrong_count_cannot_publish_archives(self):
        for mode in ('late','count'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises(ValueError):self.capture(root,mode=mode)
                self.assertFalse((root/'retained/transport.json').exists())
                self.assertFalse(list((root/'retained').glob('*.raw.xz')))

    def test_replay_rejects_changed_waveform_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.capture(root)
            archive=root/'retained/1.raw.xz';original=archive.read_bytes()
            write(root/'changed.raw',[(0,0),(.5,9),(1,0)])
            archive.write_bytes(lzma.compress((root/'changed.raw').read_bytes()))
            with self.assertRaises(ValueError):replay(root/'retained')
            archive.write_bytes(original)
            (root/'retained/1.log.xz').write_bytes(lzma.compress(b'No. of Data Rows : 4\n'))
            with self.assertRaises(ValueError):replay(root/'retained')


if __name__=='__main__':unittest.main()
