import json
from pathlib import Path
import unittest
from postreset_adc_capture import experiment, STEPS
from postreset_refinement_capture import ORIGINAL_TRAN

HERE = Path(__file__).resolve().parent


class ADCCaptureTests(unittest.TestCase):
    def setUp(self):
        root = HERE/'reports/postreset-startup-fixes/combined'
        self.deck = (root/'io.cir').read_text()
        self.environment = json.loads((root/'run.json').read_text())['environment']

    def test_matched_controls_preserve_full_reset_stimulus_and_all_other_options(self):
        original = dict(self.environment)
        for step in STEPS:
            for mode in ('off', 'on'):
                deck, env = experiment(self.deck, self.environment, step, mode)
                self.assertEqual(deck.replace(f'\n.tran {step:g}n 1.16e+06n\n', ORIGINAL_TRAN), self.deck)
                expected = dict(original)
                if mode == 'on': expected['ROBOTRON_ADC_CROSSINGS'] = '1'
                self.assertEqual(env, expected)
        self.assertEqual(self.environment, original)

    def test_coarse_control_cannot_bypass_window_validation(self):
        for bad in (self.deck.replace('1.16e+06n', '20000n'),
                    self.deck.replace('1000000n 0 1000001n 5', '1n 0 2n 5'),
                    self.deck+'\n.tran 1n 1u\n'):
            for step in STEPS:
                with self.assertRaises(ValueError): experiment(bad, self.environment, step, 'on')

    def test_rejects_ambiguous_baseline_and_unprescribed_experiments(self):
        for value in ('0', '1', 'off'):
            with self.assertRaises(ValueError):
                experiment(self.deck, dict(self.environment, ROBOTRON_ADC_CROSSINGS=value), 25, 'on')
        for step in (0, 10, float('nan'), float('inf')):
            with self.assertRaises(ValueError): experiment(self.deck, self.environment, step, 'off')
        with self.assertRaises(ValueError): experiment(self.deck, self.environment, 25, 'auto')


if __name__ == '__main__': unittest.main()
