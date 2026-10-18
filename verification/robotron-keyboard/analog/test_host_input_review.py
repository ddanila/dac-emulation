"""Conditional negative-pulse limits must not become blanket static thresholds."""
import json
import lzma
import tempfile
from pathlib import Path
import unittest
from host_input_review import review, firmware_samples

LIMITS=json.loads(Path(__file__).with_name('d104_limits.json').read_text())['input']

class InputReviewTests(unittest.TestCase):
    def test_conditional_pulse_and_unknown_duty(self):
        r=review([[0,1],[1e-9,-1.2],[2e-9,-1.2],[3e-9,1]],LIMITS)
        self.assertFalse(r['withinStaticVoltageEnvelope'])
        self.assertTrue(r['conditionalAmplitudeAndDurationSatisfied'])
        self.assertFalse(r['qualified'])
        self.assertFalse(r['dynamicDutyQualified'])
        self.assertAlmostEqual(r['negativePulses'][0]['durationSeconds'],(2+1/11)*1e-9,delta=1e-18)

    def test_amplitude_duration_and_incomplete_pulse(self):
        for rows in ([[0,1],[1e-9,-1.6],[2e-9,1]],
                     [[0,1],[1e-9,-1.2],[300e-9,-1.2],[301e-9,1]],
                     [[0,-1.2],[1e-9,1]], [[0,1],[1e-9,-1.2]]):
            self.assertFalse(review(rows,LIMITS)['conditionalAmplitudeAndDurationSatisfied'])
        r=review([[0,1],[1e-9,5.6]],LIMITS)
        self.assertTrue(r['requiresAboveMaxCurrentException'])
        self.assertFalse(r['withinStaticVoltageEnvelope'])

    def test_static_and_bad_samples(self):
        self.assertTrue(review([[0,-.8],[1e-9,5.5]],LIMITS)['withinStaticVoltageEnvelope'])
        for rows in ([],[[0,0]],[[0,0],[0,1]],[[0,0],[-1,1]],[[0,0],[1,float('nan')]]):
            with self.assertRaises(ValueError):review(rows,LIMITS)

class FirmwareInputReviewTests(unittest.TestCase):
    signals = ['v(cable_data,g)', 'v(cable_clock,g)',
               'v(host_data_buffer_input,host_receiver_gnd)',
               'v(host_clock_buffer_input,host_receiver_gnd)',
               'v(host_data_buffer_output,host_receiver_gnd)',
               'v(host_clock_buffer_output,host_receiver_gnd)']

    def capture(self, directory, rows, header=None):
        path = Path(directory) / 'host-trace.txt'
        text = ' '.join(['time', *(header or self.signals)]) + '\n'
        text += '\n'.join(' '.join(map(str, row)) for row in rows) + '\n'
        Path(str(path) + '.xz').write_bytes(lzma.compress(text.encode()))
        return path

    def test_input_nodes_not_cable_or_buffer_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.capture(directory, [[0,-9,-9,1,1,9,9],
                [1e-9,-9,-9,-1.6,2,9,9], [2e-9,-9,-9,1,2,9,9]])
            data = review(firmware_samples(path,self.signals,0,2e-9,1),LIMITS)
            clock = review(firmware_samples(path,self.signals,1,2e-9,1),LIMITS)
            self.assertEqual(data['minV'],-1.6)
            self.assertFalse(data['conditionalAmplitudeAndDurationSatisfied'])
            self.assertTrue(clock['withinStaticVoltageEnvelope'])
            self.assertFalse(clock['qualified'])

    def test_truncated_gapped_reordered_and_nonfinite_captures_fail(self):
        good = [[0,1,1,1,1,1,1], [1e-9,1,1,1,1,1,1], [2e-9,1,1,1,1,1,1]]
        variants = [good[:-1], good[1:], [good[0],good[2]],
                    [good[0],good[0],good[2]], [good[0],good[2],good[1]],
                    [good[0], [1e-9,1,1,1,float('nan'),1,1], good[2]]]
        with tempfile.TemporaryDirectory() as directory:
            for rows in variants:
                path = self.capture(directory, rows)
                with self.assertRaises(ValueError):
                    review(firmware_samples(path,self.signals,0,2e-9,1),LIMITS)
            path = self.capture(directory, good, list(reversed(self.signals)))
            with self.assertRaises(ValueError):
                list(firmware_samples(path,self.signals,0,2e-9,1))
            with self.assertRaises(ValueError):
                list(firmware_samples(path,list(reversed(self.signals)),0,2e-9,1))

if __name__=='__main__':unittest.main()
