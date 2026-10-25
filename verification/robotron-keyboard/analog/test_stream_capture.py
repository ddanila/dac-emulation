import os
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
if mode=='flood':print('audit line\\n'*20000,flush=True)
with os.fdopen(int(sys.argv[1]),'wb') as raw,open(sys.argv[2],'rb') as source:
 for chunk in iter(lambda:source.read(37),b''):raw.write(chunk);raw.flush()
print('No. of Data Rows : '+('4' if mode=='count' else (sys.argv[4] if len(sys.argv)>4 else '3')),flush=True)
if mode=='late':raise SystemExit(8)
'''


class StreamCaptureTests(unittest.TestCase):
    def execute(self,root,mode='ok',timeout=10):
        source=root/'source.raw';write(source,[(0,0),(.5,2),(1,0)])
        commands=[lambda fd,i=i:([sys.executable,'-c',WORKER,str(fd),str(source),mode if i==1 else 'ok'],root) for i in range(3)]
        return run(commands,root/'out',os.environ.copy(),1,timeout)

    def test_full_middle_fanout_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=self.execute(root)
            self.assertTrue(result['completed']);self.assertFalse(result['qualified'])
            self.assertEqual(len(result['streams']),3)
            self.assertTrue(all(c['maximumVoltageDifference']==0 for c in result['comparisons']))
            self.assertFalse(list((root/'out').glob('*.raw')))

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
