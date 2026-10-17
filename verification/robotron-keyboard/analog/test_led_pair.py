import tempfile
import unittest
from pathlib import Path
from compare_led_pair import compare_edges, edges


class LedPairTests(unittest.TestCase):
    def event(self, stamp, direction='rise', channel=0):
        return {'channel': channel, 'direction': direction,
                'earliestSeconds': stamp * 1e-9, 'latestSeconds': (stamp + 1) * 1e-9}

    def test_same_states_cannot_hide_phase_shift(self):
        a = [self.event(10), self.event(50, 'fall')]
        b = [self.event(30), self.event(70, 'fall')]
        r = compare_edges(a, b, 15)
        self.assertFalse(r['passed'])
        self.assertEqual(r['firstDifference']['ordinal'], 0)
        self.assertAlmostEqual(r['maximumBracketDifferenceNs'], 21)

    def test_missing_reversed_and_absent_edges_fail(self):
        for a, b in [([self.event(10)], []), ([], []),
                     ([self.event(10)], [self.event(10, 'fall')])]:
            self.assertFalse(compare_edges(a, b, 15)['passed'])

    def test_matching_brackets_pass_and_wide_brackets_fail(self):
        a = self.event(10)
        self.assertTrue(compare_edges([a], [a], 15)['passed'])
        a['latestSeconds'] = 40e-9
        self.assertFalse(compare_edges([a], [a], 15)['passed'])

    def test_channels_and_printed_time_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'trace.txt'
            p.write_text('time siso caps i1 i2\n1.00000e-3 0 5 0 0\n1.00001e-3 5 0 0 0\n')
            result = list(edges(p, 10))
            self.assertEqual([(e['channel'],e['direction']) for e in result], [(0,'rise'),(1,'fall')])
            self.assertAlmostEqual((result[0]['latestSeconds']-result[0]['earliestSeconds'])*1e9,20)

    def test_missing_subnanosecond_sample_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'trace.txt'
            p.write_text('time siso caps i1 i2\n0 0 0 0 0\n1.25000000000000000e-10 5 5 0 0\n')
            with self.assertRaisesRegex(ValueError,'timestep'):
                list(edges(p,.0625))


if __name__ == '__main__':
    unittest.main()
