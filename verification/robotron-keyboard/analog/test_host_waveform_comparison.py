"""Absolute-time interpolation must retain narrow peaks and mismatched extents."""
import unittest
import math
import tempfile
from pathlib import Path
from host_waveform_comparison import compare_samples, rows


class WaveformComparisonTests(unittest.TestCase):
    def test_different_knots_on_same_line(self):
        r=compare_samples([(0,0),(2,4)],[(0,0),(1,2),(2,4)])
        self.assertEqual(r['signals'][0]['maximumDifferenceV'],0)
        self.assertEqual(r['signals'][0]['rmsDifferenceV'],0)
        self.assertEqual(r['unionKnots'],3)

    def test_narrow_peak_on_either_grid_is_not_discarded(self):
        flat=[(0,0,2),(2,0,2)]
        peak=[(0,0,2),(.9,0,2),(1,5,2),(1.1,0,2),(2,0,2)]
        for a,b in ((flat,peak),(peak,flat)):
            r=compare_samples(a,b)
            self.assertEqual(r['signals'][0]['maximumDifferenceV'],5)
            self.assertEqual(r['signals'][0]['timeSeconds'],1)
            self.assertEqual(r['signals'][1]['maximumDifferenceV'],0)
            self.assertAlmostEqual(r['signals'][0]['integratedAbsoluteDifferenceVoltSeconds'],.5)
            self.assertAlmostEqual(r['signals'][0]['meanAbsoluteDifferenceV'],.25)
            self.assertAlmostEqual(r['signals'][0]['rmsDifferenceV'],math.sqrt(5/6))

    def test_signed_crossing_does_not_cancel_absolute_error(self):
        # Difference -2 -> +4 crosses zero after one second. The two
        # triangles have areas 1 and 4; the squared-error integral is 12.
        for fine in ([(0,-2),(3,4)], [(0,-2),(1,0),(2,2),(3,4)]):
            r=compare_samples([(0,0),(3,0)],fine)['signals'][0]
            self.assertAlmostEqual(r['integratedAbsoluteDifferenceVoltSeconds'],5)
            self.assertAlmostEqual(r['meanAbsoluteDifferenceV'],5/3)
            self.assertAlmostEqual(r['rmsDifferenceV'],2)

    def test_constant_error_retains_duration_and_multiple_signals(self):
        r=compare_samples([(0,3,-2),(4,3,-2)],[(0,0,0),(4,0,0)])
        for entry, magnitude in zip(r['signals'],(3,2)):
            self.assertEqual(entry['integratedAbsoluteDifferenceVoltSeconds'],4*magnitude)
            self.assertEqual(entry['meanAbsoluteDifferenceV'],magnitude)
            self.assertEqual(entry['rmsDifferenceV'],magnitude)

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
