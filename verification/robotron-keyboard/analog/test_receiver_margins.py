#!/usr/bin/env python3
"""Ensure correct received bits alone cannot pass electrical margin qualification."""
import tempfile
import unittest
from pathlib import Path

from receiver_margins import measure


class ReceiverMarginTests(unittest.TestCase):
    def run_trace(self, values, received=((250000, 1),), step=25, budget=100, time_format=None, inverted_data=True):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.txt'
            stamp = lambda t: format(t * 1e-9, time_format) if time_format else str(t * 1e-9)
            trace.write_text('time data clock\n' + '\n'.join(f'{stamp(t)} {v} 0' for t, v in values) + '\n')
            return measure(trace, received, step, budget, inverted_data=inverted_data)

    def test_stable_interval_and_censored_ends(self):
        result = self.run_trace([(t, 0) for t in range(0, 501, 25)])
        self.assertTrue(result['withinBudget'])
        self.assertAlmostEqual(result['minimumSampledSetupNs'], 250)
        self.assertAlmostEqual(result['minimumSampledHoldNs'], 250)
        self.assertTrue(result['events'][0]['leftCensored'])
        self.assertTrue(result['events'][0]['rightCensored'])

    def test_unknown_voltage_near_edge_breaks_margin(self):
        for bad_time in (200, 300):
            with self.subTest(bad_time=bad_time):
                result = self.run_trace([(t, 1.4 if t == bad_time else 0) for t in range(0, 501, 25)])
                self.assertFalse(result['withinBudget'])

    def test_wrong_data_missing_samples_and_missing_activity_rejected(self):
        cases = [([(t, 5) for t in range(0, 501, 25)], ((250000, 1),)),
                 ([(0, 0), (500, 0)], ((250000, 1),)),
                 ([(t, 0) for t in range(0, 501, 25)], ())]
        for values, received in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.run_trace(values, received)

    def test_long_trace_printed_rounding_is_not_a_missing_sample(self):
        values = [(1000000000+t, 0) for t in range(0, 501, 25)]
        result = self.run_trace(values, ((1000000250000, 1),), time_format='.8e')
        self.assertTrue(result['withinBudget'])
        self.assertAlmostEqual(result['maximumTimestampUncertaintyNs'], 5, places=5)
        self.assertAlmostEqual(result['minimumSampledSetupNs'], 245, places=5)
        self.assertAlmostEqual(result['minimumSampledHoldNs'], 245, places=5)
        self.assertGreater(result['maximumSampleGapNs'], 29)
        with self.assertRaisesRegex(ValueError, 'timestep'):
            self.run_trace([row for row in values if row[0] != 1000000250],
                           ((1000000250000, 1),), time_format='.8e')

    def test_timestamp_rounding_cannot_manufacture_margin(self):
        result = self.run_trace([(1000000000+t, 0) for t in range(0, 201, 25)],
                                ((1000000100000, 1),), time_format='.8e')
        self.assertFalse(result['withinBudget'])
        self.assertLess(result['minimumSampledSetupNs'], 96)
        self.assertLess(result['minimumSampledHoldNs'], 96)

    def test_host_buffer_uses_noninverted_data(self):
        values = [(t, 5) for t in range(0, 501, 25)]
        self.assertTrue(self.run_trace(values, inverted_data=False)['withinBudget'])
        with self.assertRaises(ValueError):
            self.run_trace(values, inverted_data=True)

    def test_valid_high_wire_is_logical_zero(self):
        result = self.run_trace([(t, 5) for t in range(0, 501, 25)], ((250000, 0),))
        self.assertTrue(result['withinBudget'])



class BoardMarginTests(unittest.TestCase):
    def test_board_polarity_hashes_and_producer_failure_are_preserved(self):
        import json
        import subprocess
        from compare_firmware_io import sha
        from serial_observation import validate_transport
        from receiver_margins import load_board_run
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'boot.cir').write_text('fixture\n.control\ntran 25n 0.0000005 0\n.endc\n.end\n')
            log='SERIAL_TX 1000 1\nSERIAL_RX 250000 1\n'
            (p/'ngspice.log').write_text(log)
            (p/'host-trace.txt').write_text('Hash-bound host capture\n')
            header='time v(cpu_clock) v(cpu_reset) v(receiver_data) v(receiver_clock)\n'
            trace=header+''.join(f'{i*1e-9:.17e} 0 5 3 0\n' for i in range(0,501,25))
            (p/'trace.txt').write_text(trace)
            report={'passed':False,'qualified':False,'error':'Independent producer gate failed',
                    'assumptions':{'hostBuffer':'7404-candidate','maximumStepNs':25,
                                   'traceWindowSeconds':[0,5e-7]},
                    'serialTransport':validate_transport(log,require_activity=True)}
            for name,key in [('boot.cir','deckSha256'),('ngspice.log','logSha256'),
                             ('host-trace.txt','hostTraceSha256'),('trace.txt','traceSha256')]:
                report[key]=sha(p/name)
            (p/'report.json').write_text(json.dumps(report))
            command=['python3',str(Path(__file__).with_name('receiver_margins.py')),str(p),
                     '--board','--required-ns','140','--out',str(p/'margins.json')]
            subprocess.run(command,check=True,capture_output=True,text=True)
            result=json.loads((p/'margins.json').read_text())
            self.assertTrue(result['passed'])
            self.assertFalse(result['qualified'])
            self.assertFalse(result['producerPassed'])
            self.assertEqual(result['producerError'],report['error'])
            self.assertFalse(result['observations']['invertedData'])
            self.assertAlmostEqual(result['observations']['minimumSampledSetupNs'],250)
            (p/'trace.txt').write_text(trace+'0.0000006 0 5 3 0\n')
            with self.assertRaisesRegex(ValueError,'trace differs'):load_board_run(p)
            (p/'trace.txt').write_text(trace)
            report['serialTransport']['received'][0]=(250000,0)
            (p/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'serial report differs'):load_board_run(p)
            report['serialTransport']=validate_transport(log,require_activity=True)
            lines=trace.splitlines(True)
            for invalid in (trace.replace('v(receiver_data)','v(wrong)'),
                            lines[0]+''.join(lines[2:]), ''.join(lines[:-1]),
                            trace.replace(' 5 3 0', ' 5 0 0')):
                (p/'trace.txt').write_text(invalid)
                report['traceSha256']=sha(p/'trace.txt')
                (p/'report.json').write_text(json.dumps(report))
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(json.loads((p/'margins.json').read_text())['passed'])


if __name__ == '__main__':
    unittest.main()
