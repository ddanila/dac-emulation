"""Absolute-time interpolation must retain narrow peaks and mismatched extents."""
import unittest
import tempfile
from pathlib import Path
from host_waveform_comparison import compare_samples, rows


class WaveformComparisonTests(unittest.TestCase):
    def test_different_knots_on_same_line(self):
        r=compare_samples([(0,0),(2,4)],[(0,0),(1,2),(2,4)])
        self.assertEqual(r['signals'][0]['maximumDifferenceV'],0)
        self.assertEqual(r['unionKnots'],3)

    def test_narrow_peak_on_either_grid_is_not_discarded(self):
        flat=[(0,0,2),(2,0,2)]
        peak=[(0,0,2),(.9,0,2),(1,5,2),(1.1,0,2),(2,0,2)]
        for a,b in ((flat,peak),(peak,flat)):
            r=compare_samples(a,b)
            self.assertEqual(r['signals'][0]['maximumDifferenceV'],5)
            self.assertEqual(r['signals'][0]['timeSeconds'],1)
            self.assertEqual(r['signals'][1]['maximumDifferenceV'],0)

    def test_phase_is_not_aligned_away(self):
        r=compare_samples([(0,0),(1,1),(2,1)],[(0,0),(1,0),(2,1)])
        self.assertEqual(r['signals'][0]['maximumDifferenceV'],1)

    def test_missing_or_different_extents_rejected(self):
        for a,b in (([],[(0,0),(1,1)]), ([(0,0)],[(0,0),(1,1)]),
                    ([(0,0),(2,0)],[(0,0),(1,0)]),
                    ([(0,0),(1,0)],[(.1,0),(1,0)])):
            with self.assertRaises(ValueError):compare_samples(a,b)

    def test_trace_parser_rejects_header_gaps_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.txt'
            for content in ('time other\n0 0\n1e-9 1\n',
                            'time v(x)\n0 0\n2e-9 1\n',
                            'time v(x)\n0 0\n1e-9 nan\n',
                            'time v(x)\n0 0\n0 1\n',
                            'time v(x)\n1e-9 0\n2e-9 1\n'):
                path.write_text(content)
                with self.assertRaises(ValueError):list(rows(path,['v(x)'],1))


if __name__=='__main__':unittest.main()
