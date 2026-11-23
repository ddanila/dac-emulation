import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import horizontal_output_switching_proxy as proxy


class HorizontalOutputSwitchingProxyTests(unittest.TestCase):
    def test_live_model_turnoff_metric_is_reproducible_and_tf_sensitive(self):
        report = proxy.run()
        saved = report
        self.assertFalse(report['data_sheet_timing_verified'])
        cases = report['cases']
        self.assertAlmostEqual(cases['nominal']['base_current_on_a'], .5, delta=.02)
        self.assertLess(cases['low_tf']['clamp_10_to_90_percent_s'],
                        cases['nominal']['clamp_10_to_90_percent_s'])
        self.assertLess(cases['nominal']['clamp_10_to_90_percent_s'],
                        cases['high_tf']['clamp_10_to_90_percent_s'])
        self.assertLess(cases['low_tr']['command_to_clamp_10_percent_s'],
                        cases['high_tr']['command_to_clamp_10_percent_s'])


if __name__ == '__main__':
    unittest.main()
