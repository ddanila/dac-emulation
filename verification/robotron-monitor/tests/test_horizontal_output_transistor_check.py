import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_output_transistor_check as check


class HorizontalOutputTransistorCheckTests(unittest.TestCase):
    def test_live_model_matches_dc_class_and_low_gain_fails(self):
        saved = json.loads((ROOT/'reference/k7222-11/horizontal-output-transistor-dc-check.json').read_text())
        report = check.run()
        self.assertEqual(report, saved)
        self.assertTrue(report['passed'])
        self.assertEqual(set(report['checks']), {'hFE_0p1a', 'hFE_4p5a', 'VCEsat_dc_proxy'})
        self.assertLess(report['saturation_dc_proxy']['collector_emitter_voltage_v'], 1)
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory)/'models.cir'
            original = check.MODELS.read_text()
            self.assertIn('HOR_OUTPUT_N NPN(IS=1e-10 BF=20 ', original)
            altered.write_text(original.replace('HOR_OUTPUT_N NPN(IS=1e-10 BF=20 ',
                                                'HOR_OUTPUT_N NPN(IS=1e-10 BF=2 '))
            previous = check.MODELS
            try:
                check.MODELS = altered
                changed = check.run()
            finally:
                check.MODELS = previous
            self.assertFalse(changed['passed'])
            self.assertFalse(changed['checks']['hFE_0p1a'])


if __name__ == '__main__':
    unittest.main()
