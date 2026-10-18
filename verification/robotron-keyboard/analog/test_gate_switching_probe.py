#!/usr/bin/env python3
"""Reject misleading propagation measurements before comparing gate limits."""
import unittest
from gate_switching_probe import crossing, delays


def waveform():
    return [[t*1e-9, a, y] for t,a,y in [
        (0,0,3),(190,0,3),(200,0,3),(201,3,3),(205,3,3),(206,3,0),
        (590,3,0),(600,3,0),(601,0,0),(605,0,0),(606,0,3),(800,0,3)]]


class MeasurementTests(unittest.TestCase):
    def test_delay_bracket_conservatively_includes_sampling(self):
        d = delays(waveform())
        for edge in d.values():
            self.assertAlmostEqual(edge['minimumNs'], 4)
            self.assertAlmostEqual(edge['maximumNs'], 6)
            self.assertTrue(edge['withinDelayLimit'])

    def test_limit_uses_worst_bracket_endpoint(self):
        d = delays(waveform(), {'tPHL':5,'tPLH':5})
        self.assertFalse(d['tPHL']['withinDelayLimit'])
        self.assertFalse(d['tPLH']['withinDelayLimit'])

    def test_missing_and_ambiguous_crossings_fail(self):
        with self.assertRaisesRegex(ValueError, 'found 0'):
            crossing([[0,0],[1,0]],1,True,0,1)
        with self.assertRaisesRegex(ValueError, 'found 2'):
            crossing([[0,0],[1,3],[2,0],[3,3]],1,True,0,3)

    def test_incomplete_or_invalid_waveform_fails(self):
        for rows in [waveform()[:-1], [[0,0,3],[float('nan'),3,0]], waveform()+[waveform()[-1]]]:
            with self.assertRaises(ValueError):
                delays(rows)


if __name__ == '__main__':
    unittest.main()
