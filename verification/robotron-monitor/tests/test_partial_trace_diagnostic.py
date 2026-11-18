from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import partial_trace_diagnostic


class PartialTraceDiagnosticTests(unittest.TestCase):
    def test_unfinished_adaptive_trace_uses_elapsed_time_for_eht_mean(self):
        names=partial_trace_diagnostic.PROBES
        rows=((0.,0.,0.,0.),(.0005,50.,100.,1.),(.0015,250.,300.,0.))
        header='Title: interrupted diagnostic\nFlags: real\nNo. Variables: 4\nNo. Points: 0\nVariables:\n'
        header+=''.join(f'{i} {name} voltage\n' for i,name in enumerate(names))+'Binary:\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.raw'
            path.write_bytes(header.encode()+b''.join(struct.pack('=4d',*row) for row in rows)+b'cut')
            report=partial_trace_diagnostic.summarize(path)
        self.assertEqual(report['qualification'],'diagnostic-only')
        self.assertEqual(report['declared_points'],0)
        self.assertEqual(report['complete_rows'],3)
        self.assertEqual(report['trailing_bytes'],3)
        self.assertAlmostEqual(report['bins'][0]['eht_time_mean_v'],100.)
        self.assertAlmostEqual(report['bins'][1]['eht_time_mean_v'],250.)
        self.assertEqual(report['bins'][0]['h_sync_upcross_100v'],1)
        self.assertEqual(report['bins'][1]['h_sync_upcross_100v'],0)


if __name__=='__main__':unittest.main()
