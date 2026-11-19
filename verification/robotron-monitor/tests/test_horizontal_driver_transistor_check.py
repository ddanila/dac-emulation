import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_driver_transistor_check as check


class HorizontalDriverTransistorCheckTests(unittest.TestCase):
    def test_live_class_proxy_and_slow_transit_regression(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-driver-transistor-class-check.json').read_text())
        report = check.run()
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(report['assembly_reference'], 'Q1036')
        self.assertGreater(report['transition_frequency_proxy_hz'], 60e6)

        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory)/'models.cir'
            original = check.MODELS.read_text()
            self.assertIn('HOR_DRIVER_N NPN(IS=1e-12 BF=60 VAF=80 CJE=20p CJC=8p TF=1n TR=100n)', original)
            altered.write_text(original.replace('CJE=20p CJC=8p TF=1n TR=100n)',
                                                'CJE=150p CJC=80p TF=20n TR=100n)'))
            previous = check.MODELS
            try:
                check.MODELS = altered
                ac_bias = check.gain_at(.01, 10)
                self.assertLess(15e6*check.ac_gain_at_15mhz(ac_bias['base_current_a']), 60e6)
                with self.assertRaisesRegex(ValueError, 'register nominal differs'):
                    check.run()
            finally:
                check.MODELS = previous


if __name__ == '__main__':
    unittest.main()
