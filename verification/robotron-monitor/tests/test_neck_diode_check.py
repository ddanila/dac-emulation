import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neck_diode_check


class NeckDiodeCheckTests(unittest.TestCase):
    def test_both_neck_profiles_supply_every_model_parameter(self):
        names = set(re.findall(r'\{([a-z_]+)\}', neck_diode_check.MODEL.read_text()))
        for filename in ('k7222-11-neck.json', 'k7222-11-neck-diagnostic.json'):
            profile = json.loads((ROOT/'profiles'/filename).read_text())
            self.assertFalse(names - set(profile['parameters']), filename)
            for name in ('d_vj', 'd_m', 'd_fc', 'd_eg', 'd_xti'):
                self.assertEqual(profile['parameters'][name],
                                 json.loads(neck_diode_check.PROFILE.read_text())['parameters'][name])

    def test_fixed_stage_copies_declare_the_same_screened_defaults(self):
        profile = json.loads(neck_diode_check.PROFILE.read_text())
        expected = {name: profile['parameters']['d_'+name.lower()]['nominal']
                    for name in ('VJ', 'M', 'FC', 'EG', 'XTI')}
        for filename in ('k7222-11-vertical-sync-models.cir',
                         'k7222-11-vertical-integrator-models.cir'):
            model = (ROOT/'circuits'/filename).read_text()
            definition = re.search(r'^\.model 1AD50_BOUND D\(([^)]*)\)',
                                   model, re.M)
            self.assertIsNotNone(definition)
            parameters = dict(re.findall(r'([A-Z]+)=([^\s)]+)', definition.group(1)))
            for name, nominal in expected.items():
                self.assertEqual(float(parameters[name]), nominal)

    def test_registered_bounds_match_live_model_profile(self):
        register = json.loads((ROOT/'reference/k7222-11/device-model-register.json').read_text())
        family = next(row for row in register['families']
                      if row['id'] == '1AD50-signal-clamp-diode')
        profile = json.loads(neck_diode_check.PROFILE.read_text())
        model = neck_diode_check.MODEL.read_text()
        definition = re.search(r'\.model 1AD50_BOUND D\(([^)]*)\)', model, re.S)
        self.assertIsNotNone(definition)
        live = dict(re.findall(r'([A-Z]+)=\{([^}]+)\}', definition.group(1)))
        self.assertEqual(set(live), set(family['parameters']))
        self.assertEqual(len(family['member_ids']), 8)
        for key, parameter in family['parameters'].items():
            self.assertEqual(live[key], parameter['profile_key'])
            spec = profile['parameters'][live[key]]
            self.assertEqual(spec['nominal'], parameter['nominal'])
            self.assertEqual([spec['minimum'], spec['maximum']], parameter['bounds'])

    def test_nominal_live_model_matches_saved_comparator_measurements(self):
        measured = neck_diode_check.run()
        saved = json.loads((ROOT/'reference/k7222-11/neck-diode-model-check.json').read_text())
        self.assertEqual(measured, saved)
        self.assertTrue(all(measured['checked'].values()))
        self.assertAlmostEqual(measured['recovery_test']['forward_current_a'], 0.01,
                               delta=0.0005)
        self.assertAlmostEqual(measured['recovery_test']['peak_reverse_current_a'], -0.06,
                               delta=0.003)


if __name__ == '__main__':
    unittest.main()
