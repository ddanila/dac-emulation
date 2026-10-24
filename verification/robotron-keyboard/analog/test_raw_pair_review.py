import struct
from pathlib import Path
import tempfile
import unittest
from raw_pair_review import compare_raw


def write(path, values, names=('time','v(x)')):
    text='Title: test\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: '+str(len(names))+'\nNo. Points: 0\nVariables:\n'
    text+=''.join(f'{i} {n} voltage\n' for i,n in enumerate(names))+'Binary:\n'
    path.write_bytes(text.encode()+b''.join(struct.pack('='+'d'*len(row),*row) for row in values))


class RawPairTests(unittest.TestCase):
    def test_union_grid_detects_peak_and_exact_rejects_changed_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            write(a,[(0,0),(1,0)]);write(b,[(0,0),(.5,.02),(1,0)])
            r=compare_raw(a,b,[2,3],1)
            self.assertEqual(r['maximumVoltageDifference'],.02)
            self.assertEqual(r['signals']['v(x)']['timeSeconds'],.5)
            with self.assertRaises(ValueError):compare_raw(a,b,[2,3],1,exact=True)

    def test_rejects_truncation_tail_missing_signal_and_short_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            write(a,[(0,0),(1,0)]);write(b,[(0,0),(1,0)])
            self.assertTrue(compare_raw(a,b,[2,2],1,exact=True)['allSamplesExactlyEqual'])
            original=b.read_bytes()
            for data in (original[:-1],original+b'x'):
                b.write_bytes(data)
                with self.assertRaises(ValueError):compare_raw(a,b,[2,2],1)
            write(b,[(0,0),(1,0)],('time','v(y)'))
            with self.assertRaises(ValueError):compare_raw(a,b,[2,2],1)
            write(b,[(0,0),(1,0)])
            with self.assertRaises(ValueError):compare_raw(a,b,[2,2],2)


if __name__=='__main__':unittest.main()
