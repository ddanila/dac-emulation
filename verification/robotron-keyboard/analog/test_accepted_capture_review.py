#!/usr/bin/env python3
import unittest
from accepted_capture_review import prefix
from host_waveform_comparison import compare_samples

class PrefixTests(unittest.TestCase):
    def test_boundary_interpolation_retains_knots(self):
        self.assertEqual(list(prefix([(0,0,2),(1,4,4),(2,8,6)],1.5)),
                         [(0,0,2),(1,4,4),(1.5,6,5)])
        self.assertEqual(list(prefix([(0,0),(1,4),(2,8)],1)), [(0,0),(1,4)])

    def test_no_extrapolation(self):
        for stop in (-1,3):
            with self.assertRaises(ValueError): list(prefix([(0,0),(2,8)],stop))
        with self.assertRaises(ValueError): list(prefix([],1))

    def test_common_prefix_keeps_real_difference(self):
        result = compare_samples(prefix([(0,0),(1,2),(2,4)],1.5),
                                 prefix([(0,0),(.5,2),(1.5,6)],1.5))
        self.assertEqual(result['endSeconds'],1.5)
        self.assertEqual(result['signals'][0]['maximumDifferenceV'],3)
        self.assertEqual(result['signals'][0]['timeSeconds'],1.5)

if __name__ == '__main__': unittest.main()
