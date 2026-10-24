import struct
import tempfile
from pathlib import Path
import unittest
from live_raw_review import compare_trace, signal_name


class LiveRawReviewTests(unittest.TestCase):
    def test_special_current_names_follow_ngspice_writer(self):
        self.assertEqual(signal_name('i(@Bwr_low[i])'), '@bwr_low[i]')
        self.assertEqual(signal_name('@Bwr_low[i]'), '@bwr_low[i]')
        self.assertEqual(signal_name('i(Vdriver_supply)'), 'i(vdriver_supply)')
        self.assertEqual(signal_name('i(@device[v])'), 'i(@device[v])')

    def test_reordered_columns_preserve_every_sample(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            raw=p/'trace.raw';text=p/'trace.txt'
            raw.write_bytes(b'Title: test\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 3\nNo. Points: 0\nVariables:\n0 time time\n1 v(a) voltage\n2 i(v1) current\nBinary:\n'+struct.pack('=6d',0,5,.01,1,4,.02))
            text.write_text('time i(V1) v(a)\n0 .01 5\n1 .02 4\n')
            self.assertTrue(compare_trace(raw,text,2)['allSamplesExactlyEqual'])
            for bad in ('time i(V1) v(a)\n0 .01 5\n1 .02 4.000000000000001\n',
                        'time i(V1) v(a)\n0 .01 5\n',
                        'time v(missing)\n0 5\n1 4\n'):
                text.write_text(bad)
                with self.assertRaises(ValueError):compare_trace(raw,text,2)


if __name__=='__main__':
    unittest.main()
