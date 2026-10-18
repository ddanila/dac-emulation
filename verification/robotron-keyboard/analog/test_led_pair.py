import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import compare_led_pair
from test_firmware_io_comparison import report
from serial_observation import validate_transport
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

    def test_host_cli_preserves_opt_in_timing_and_qualification_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'comparison.json'
            coarse, fine = report(10), report(5)
            for r in (coarse, fine):
                r['assumptions'].update(hostBuffer='7404-candidate', ledTrace=True)
                r['qualified'] = False
                r['sources'].update({name: 'same' for name in
                    ('host_receiver.py', 'host_receiver.json', 'ttl7404_nominal.cir', 'd104_limits.json')})
            transport = validate_transport('SERIAL_TX 1000 1\nSERIAL_RX 21000 1\n', True)
            events = [self.event(10, channel=0), self.event(10, channel=1)]
            for mode in ('default', 'experimental', 'shifted', 'claimed-qualified'):
                fine['qualified'] = mode == 'claimed-qualified'
                right = ([self.event(40, channel=0), self.event(40, channel=1)]
                         if mode == 'shifted' else events)
                argv = ['compare_led_pair.py', 'coarse', 'fine', '--out', str(output)]
                if mode != 'default':
                    argv.append('--experimental-host')
                with self.subTest(mode=mode), patch('sys.argv', argv), \
                     patch.object(compare_led_pair, 'normalized_deck', return_value='same'), \
                     patch.object(compare_led_pair, 'sha', return_value='same'), \
                     patch.object(compare_led_pair, 'load_run', side_effect=[(coarse, transport), (fine, transport)]), \
                     patch.object(compare_led_pair, 'edges', side_effect=[events, right]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    if mode == 'experimental':
                        compare_led_pair.main()
                    else:
                        with self.assertRaises(ValueError):
                            compare_led_pair.main()
                result = json.loads(output.read_text())
                self.assertEqual(result['passed'], mode == 'experimental')
                if mode != 'default':
                    self.assertIs(result['qualified'], False)

    def test_missing_subnanosecond_sample_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'trace.txt'
            p.write_text('time siso caps i1 i2\n0 0 0 0 0\n1.25000000000000000e-10 5 5 0 0\n')
            with self.assertRaisesRegex(ValueError,'timestep'):
                list(edges(p,.0625))


if __name__ == '__main__':
    unittest.main()
