"""Conditional negative-pulse limits must not become blanket static thresholds."""
import json
from pathlib import Path
import unittest
from host_input_review import review

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

if __name__=='__main__':unittest.main()
