import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import regulator5_transistor_check as check


class Regulator5TransistorCheckTests(unittest.TestCase):
    def test_live_model_matches_family_and_old_charge_model_fails(self):
        saved = json.loads((ROOT/'reference/k7222-11/regulator5-transistor-class-check.json').read_text())
        report = check.run()
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(report['assembly_source_id'], '012-6931:V4')

        original = check.MODELS.read_text()
        self.assertIn('CJE=20p CJC=8p TF=1n TR=100n ', original)
        with tempfile.TemporaryDirectory() as directory:
            slow = Path(directory)/'models.cir'
            slow.write_text(original.replace('CJE=20p CJC=8p TF=1n TR=100n ',
                                             'CJE=40p CJC=15p TF=20n TR=100n ')
                            .replace('{reg5_bf}', '60'))
            bias = check.bench.gain_at(.01, 10, check.MODEL, slow)
            ft = 15e6*check.bench.ac_gain_at(bias['base_current_a'], 10, 15e6,
                                            check.MODEL, slow)
            self.assertLess(ft, 60e6)


if __name__ == '__main__':
    unittest.main()
