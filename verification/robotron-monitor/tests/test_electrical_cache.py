import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import electrical_cache as cache

class CacheTests(unittest.TestCase):
    def fake_solver(self,text,out,runtime,timeout_s):
        out=Path(out);out.mkdir(parents=True)
        (out/'run.cir').write_text(text)
        (out/'solver.log').write_text('fixture');(out/'process.log').write_text('fixture')
        result=dict(status='complete',elapsed_s=1,full_monitor_qualified=False)
        (out/'solve.json').write_text(json.dumps(result))
        header=b'Title: fixture\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 v(x) voltage\nBinary:\n'
        (out/'trace.raw').write_bytes(header+struct.pack('=4d',0,0,.01,1))
        return result

    def test_hit_invalidation_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);receipt=dict(files={'solver':'one'})
            with mock.patch.object(cache.monitor_runtime,'verify',return_value=(None,receipt)), \
                 mock.patch.object(cache.steady_supply,'solve',side_effect=self.fake_solver) as solver:
                deck='fixture\n.tran .001 .01\n.end\n'
                a=cache.solve(deck,root/'a',root,timeout_s=60,cache=root/'cache')
                b=cache.solve(deck,root/'b',root,timeout_s=60,cache=root/'cache')
                self.assertFalse(a['cache_hit']);self.assertTrue(b['cache_hit']);self.assertEqual(solver.call_count,1)
                self.assertFalse(b['full_monitor_qualified'])
                c=cache.solve(deck+'\n',root/'c',root,timeout_s=60,cache=root/'cache')
                self.assertNotEqual(a['cache_key'],c['cache_key'])
                receipt['files']['solver']='two'
                d=cache.solve(deck,root/'d',root,timeout_s=60,cache=root/'cache')
                self.assertNotEqual(a['cache_key'],d['cache_key'])
                (root/'cache'/d['cache_key']/'trace.raw').write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):
                    cache.solve(deck,root/'e',root,timeout_s=60,cache=root/'cache')
                self.assertFalse((root/'e').exists())

    def test_successful_exit_with_truncated_trace_is_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with mock.patch.object(cache.monitor_runtime,'verify',return_value=(None,{})), \
                 mock.patch.object(cache.steady_supply,'solve',side_effect=self.fake_solver):
                with self.assertRaisesRegex(ValueError,'truncated'):
                    cache.solve('fixture\n.tran .001 .02\n.end\n',root/'a',root,timeout_s=60,cache=root/'cache')
            self.assertFalse(list((root/'cache').glob('*/cache.json')))

if __name__=='__main__':unittest.main()
