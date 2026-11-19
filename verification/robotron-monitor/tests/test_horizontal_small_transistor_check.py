import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_small_transistor_check as check


class HorizontalSmallTransistorCheckTests(unittest.TestCase):
    def test_live_models_and_historical_regressions(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-small-transistor-class-check.json').read_text())
        report = check.run()
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual([row['assembly_reference'] for row in report['devices']],
                         ['Q1034', 'Q1035'])

        original = check.MODELS.read_text()
        with tempfile.TemporaryDirectory() as directory:
            slow = Path(directory)/'models.cir'
            self.assertIn('SC237E_N NPN(IS=1e-14 BF=300 ', original)
            self.assertIn('HOR_N NPN(IS=1e-14 BF=100 VAF=80 CJE=20p CJC=8p TF=2n', original)
            slow.write_text(original.replace('SC237E_N NPN(IS=1e-14 BF=300 ',
                                             'SC237E_N NPN(IS=1e-14 BF=100 ')
                            .replace('CJE=20p CJC=8p TF=2n TR=10n)',
                                     'CJE=20p CJC=8p TF=20n TR=10n)'))
            previous = check.bench.MODELS
            try:
                check.bench.MODELS = slow
                gain = check.bench.gain_at(.002, 6, 'SC237E_N')
                self.assertLess(gain['hFE'], 224)
                bias = check.bench.gain_at(.01, 10, 'HOR_N')
                ft = 15e6*check.bench.ac_gain_at(bias['base_current_a'], 10, 15e6, 'HOR_N')
                self.assertLess(ft, 60e6)
            finally:
                check.bench.MODELS = previous


if __name__ == '__main__':
    unittest.main()
