import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_render
import steady_trace


class SteadyTraceTests(unittest.TestCase):
    def raw(self, path, *, complete=True):
        names=('time',*steady_trace.PROBES)
        rows=[(t,10000+1000*t,350,200,10,.1*t,.2*t,20e-6) for t in (0,.005,.01,.02)]
        header=f'Title: export fixture\nFlags: real\nNo. Variables: 8\nNo. Points: {len(rows) if complete else 0}\nVariables:\n'
        header+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
        path.write_bytes(header.encode()+b''.join(struct.pack('=8d',*row) for row in rows))

    def test_exact_boundary_interpolation_and_no_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.raw(root/'trace.raw')
            r=steady_trace.export(root/'trace.raw',root/'field.csv',start_s=.003,end_s=.015)
            rows=beam_render.read_trace(root/'field.csv')
            self.assertEqual(rows[0][0],0)
            self.assertAlmostEqual(rows[-1][0],.012)
            self.assertAlmostEqual(rows[0][1],10003)
            self.assertAlmostEqual(rows[-1][1],10015)
            self.assertAlmostEqual(rows[-1][5],.0015)
            self.assertFalse(r['electrical_settling_verified'])
            self.assertFalse(r['full_monitor_qualified'])
            self.assertEqual(json.loads((root/'field.json').read_text()),r)
            with self.assertRaises(FileExistsError):steady_trace.export(root/'trace.raw',root/'field.csv',start_s=.003,end_s=.015)

    def test_incomplete_solver_and_uncovered_window_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.raw(root/'trace.raw',complete=False)
            with self.assertRaises(ValueError):steady_trace.export(root/'trace.raw',root/'bad.csv',start_s=0,end_s=.02)
            self.assertFalse((root/'bad.json').exists())
            self.raw(root/'trace.raw')
            with self.assertRaises(ValueError):steady_trace.export(root/'trace.raw',root/'short.csv',start_s=0,end_s=.03)
            with self.assertRaises(ValueError):steady_trace.export(root/'trace.raw',root/'nan.csv',start_s=0,end_s=math.nan)

if __name__=='__main__':unittest.main()
