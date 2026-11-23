"""The exact MAA723 load check must reject the former under-driven proxy."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maa723_model_check as check


class MAA723ModelTests(unittest.TestCase):
    def test_saved_class_response_matches_live_model(self):
        saved = check.run()
        self.assertTrue(saved['passed'])
        high_loss = saved['engineering_150ma_probe']
        self.assertGreater(high_loss['ideal_5v_pass_power_w_at_12v'],
                           high_loss['tesla_maa723_package_power_max_w'])
        self.assertLess(abs(saved['line_regulation_v']['12_to_40']), .01)
        lower_loss = saved['lower_dissipation_150ma_probe']['observed']
        self.assertGreater(lower_loss['load_current_a'], .145)
        self.assertLess(lower_loss['chip_power_proxy_w'], .8)

    def test_old_drive_would_fail_50ma_load(self):
        _, entry = check.registered_parameters()
        parameters = json.loads(json.dumps(entry['parameters']))
        parameters['m723_error_gm']['nominal'] = 0.001
        parameters['m723_drive_limit']['nominal'] = 0.0002
        weak = check.op(parameters, supply=12, load_ohm=100)
        self.assertLess(weak['output_v'], 4.9)


if __name__ == '__main__':
    unittest.main()
