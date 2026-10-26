import os
import json
import lzma
from pathlib import Path
import sys
import tempfile
import unittest
from stream_capture import run
from test_raw_pair_review import write

WORKER='''
import os,sys,time
mode=sys.argv[3]
if mode=='early':raise SystemExit(7)
if mode=='stall':time.sleep(30)
if mode=='longline':print('x'*20000,flush=True)
if mode=='flood':print('audit line\\n'*20000,flush=True)
with os.fdopen(int(sys.argv[1]),'wb') as raw,open(sys.argv[2],'rb') as source:
 for chunk in iter(lambda:source.read(37),b''):raw.write(chunk);raw.flush()
print('No. of Data Rows : '+('4' if mode=='count' else (sys.argv[4] if len(sys.argv)>4 else '3')),flush=True)
if mode=='late':raise SystemExit(8)
'''


class StreamCaptureTests(unittest.TestCase):
    def execute(self,root,mode='ok',timeout=10,**limits):
        source=root/'source.raw';write(source,[(0,0),(.5,2),(1,0)])
        commands=[lambda fd,i=i:([sys.executable,'-c',WORKER,str(fd),str(source),mode if i==1 else 'ok'],root) for i in range(3)]
        return run(commands,root/'out',os.environ.copy(),1,timeout,**limits)

    def test_full_middle_fanout_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=self.execute(root)
            self.assertTrue(result['completed']);self.assertFalse(result['qualified'])
            self.assertEqual(len(result['streams']),3)
            self.assertTrue(all(c['maximumVoltageDifference']==0 for c in result['comparisons']))
            self.assertFalse(list((root/'out').glob('*.raw')))

    def test_log_budgets_fail_closed(self):
        cases=[('flood',{'max_log_bytes':1000}),
               ('ok',{'max_compressed_log_bytes':10}),
               ('longline',{'max_log_line_bytes':1000})]
        for mode,limits in cases:
            with self.subTest(limits=limits),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises(ValueError):self.execute(root,mode,**limits)
                failure=json.loads((root/'out/failure.json').read_text())
                self.assertFalse(failure['completed'])
                self.assertIn('budget',failure['detail'])
                self.assertFalse((root/'out/transport.json').exists())
                self.assertFalse(list((root/'out').glob('*.log.xz')))
                if 'max_compressed_log_bytes' in limits:
                    self.assertLessEqual(sum(p.stat().st_size for p in (root/'out').glob('*.partial')),limits['max_compressed_log_bytes'])

    def test_budget_receipt_matches_retained_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=self.execute(root)
            paths=list((root/'out').glob('*.log.xz'))
            self.assertEqual(result['logUsage']['compressedLogBytes'],sum(p.stat().st_size for p in paths))
            self.assertEqual(result['logUsage']['logicalLogBytes'],sum(len(lzma.decompress(p.read_bytes())) for p in paths))

    def test_invalid_limits_rejected_before_launch(self):
        for value in (0,-1,True,1.5):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises(ValueError):self.execute(root,max_log_bytes=value)
                self.assertFalse((root/'out').exists())

    def test_backpressure_with_large_logs_and_raw_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.raw'
            count=20001;write(source,[(i/(count-1),i%2) for i in range(count)])
            commands=[lambda fd:([sys.executable,'-c',WORKER,str(fd),str(source),'flood',str(count)],root) for _ in range(3)]
            result=run(commands,root/'out',os.environ.copy(),1,20)
            self.assertTrue(result['completed'])
            self.assertTrue(all(s['samples']==count for s in result['streams']))

    def test_failures_and_timeout_cannot_publish_success_or_deadlock(self):
        for mode in ('early','late','count','stall'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with self.assertRaises((ValueError,TimeoutError)):self.execute(root,mode,.5 if mode=='stall' else 10)
                self.assertTrue((root/'out/failure.json').exists())
                self.assertFalse((root/'out/transport.json').exists())
                self.assertFalse(list((root/'out').glob('*.log.xz')))

if __name__=='__main__':unittest.main()
