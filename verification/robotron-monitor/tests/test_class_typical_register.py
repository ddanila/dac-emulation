import json
import hashlib
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REF = ROOT/'reference/k7222-11'
import electrothermal
import steady_supply


class ClassTypicalRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.register = json.loads((REF/'class-typical-register.json').read_text())
        cls.by_id = {row['id']: row for row in cls.register['entries']}

    def test_entries_have_sources_bounds_and_unique_ids(self):
        register = self.register
        self.assertEqual(register['format'], 'dac-monitor-class-typical-register-v1')
        self.assertIn('partial', register['status'])
        self.assertEqual(len(self.by_id), len(register['entries']))
        for row in register['entries']:
            self.assertTrue(row['stage'] and row['model_ref'] and row['basis'])
            self.assertTrue(row['sources'])
            self.assertTrue(all(key in register['sources'] for key in row['sources']))
            low, high = row['bounds']
            self.assertTrue(all(math.isfinite(value) for value in (low, row['value'], high)))
            self.assertLessEqual(low, row['value'])
            self.assertLessEqual(row['value'], high)
        self.assertTrue(register['open_families'])

    def test_device_and_instrument_rows_match_live_sources(self):
        devices = json.loads((REF/'device-model-register.json').read_text())
        for device in devices['devices']:
            for key, parameter in device['parameters'].items():
                row = self.by_id[device['id']+'.'+key]
                if 'active_nominal' in parameter:
                    self.assertEqual(row['value'], parameter['active_nominal'])
                    self.assertEqual(row['bounds'], parameter['active_bounds'])
                    self.assertEqual(row['qualification'], parameter['active_tier'])
                else:
                    self.assertEqual(row['value'], parameter['nominal'])
                    self.assertEqual(row['bounds'], parameter['bounds'])
        for family in devices.get('families', []):
            self.assertTrue(family['member_ids'])
            profile = (json.loads((ROOT/family['profile']).read_text())
                       if family.get('profile') else None)
            for key, parameter in family['parameters'].items():
                row = self.by_id[family['id']+'.'+key]
                self.assertEqual(row['value'], parameter['nominal'])
                self.assertEqual(row['bounds'], parameter['bounds'])
                if profile and 'profile_key' in parameter:
                    live = profile['parameters'][parameter['profile_key']]
                    self.assertEqual(row['value'], live['nominal'])
                    self.assertEqual(row['bounds'], [live['minimum'], live['maximum']])
                if 'shared_model_parameter_with' in row:
                    shared = self.by_id[row['shared_model_parameter_with']]
                    self.assertEqual(row['model_ref'], shared['model_ref'])
                    self.assertEqual(row['value'], shared['value'])
                    self.assertEqual(row['bounds'], shared['bounds'])
        instrument = json.loads((REF/'service-instrument.json').read_text())
        for key in ('vertical_bandwidth_hz', 'direct_input_resistance_ohm',
                    'direct_input_capacitance_f'):
            row = self.by_id['service-instrument.'+key]
            self.assertEqual(row['value'], instrument[key]['value'])
            self.assertEqual(row['bounds'], instrument[key]['bounds'])
        sources = {item['file']: item['sha256'] for item in
                   json.loads((ROOT/'sources.json').read_text())['sources']}
        self.assertEqual(self.register['sources']['b31_g_outline']['sha256'],
                         sources['b31-g-outline.gif'])

    def test_vertical_diode_register_covers_every_live_spice_parameter(self):
        devices = json.loads((REF/'device-model-register.json').read_text())
        family = next(row for row in devices['families']
                      if row['id'] == '1AE15-vertical-signal-diode')
        model_file = ROOT/family['model_file']
        match = re.search(r'^\.model VERTICAL_DIODE D\(([^)]*)\)',
                          model_file.read_text(), re.M)
        self.assertIsNotNone(match)
        actual = dict(re.findall(r'([A-Z]+)=([0-9.eE+-]+[a-zA-Z]?)', match.group(1)))
        self.assertEqual(set(actual), set(family['parameters']))
        suffix = {'n': 1e-9, 'p': 1e-12, 'u': 1e-6}
        for key, value in actual.items():
            scale = suffix.get(value[-1], 1)
            numeric = float(value[:-1] if scale != 1 else value)*scale
            self.assertAlmostEqual(numeric, family['parameters'][key]['nominal'])

    def test_t3_assumed_rows_match_live_winding_hypothesis(self):
        winding = json.loads((REF/'t3-initial-parameters.json').read_text())['groups']
        expected = {
            'high_voltage_turns': winding['high_voltage'][0]['turns'],
            'high_voltage_resistance_ohm': winding['high_voltage'][0]['resistance_ohm'],
        }
        for key, parameter in expected.items():
            row = self.by_id['012-6921:T3.'+key]
            self.assertEqual(row['value'], parameter['value'])
            self.assertEqual(row['bounds'], [parameter['minimum'], parameter['maximum']])
            self.assertEqual(row['qualification'], parameter['evidence'])
        turns = [section['turns'] for section in winding['drive']]
        row = self.by_id['012-6921:T3.drive_total_turns']
        self.assertEqual(row['value'], sum(item['value'] for item in turns))
        self.assertEqual(row['bounds'], [sum(item['minimum'] for item in turns),
                                          sum(item['maximum'] for item in turns)])

    def test_tube_heater_class_point_matches_live_equilibrium(self):
        check=json.loads((REF/'tube-heater-class-check.json').read_text())
        source=self.register['sources']['tungsram_m31_120_1976']
        self.assertEqual(source['sha256'],check['source']['pdf_sha256'])
        self.assertFalse(check['comparator']['exact_installed_type'])
        row=self.by_id['B31G22.heater_effective_hot_resistance']
        nominal=electrothermal.parameters()
        rise=steady_supply.heater_equilibrium()['temperature_rise_k'][0]
        hot=nominal['heater_cold_ohm']*(1+nominal['heater_alpha']*rise)
        self.assertAlmostEqual(row['value'],hot,places=9)
        self.assertEqual(row['bounds'],[check['assumed_class_spread']['scenarios'][0]['hot_resistance_ohm'],
                                        check['assumed_class_spread']['scenarios'][-1]['hot_resistance_ohm']])
        self.assertLess(abs(check['comparison']['heater_current_relative_error']),.02)

    def test_tube_cutoff_comparator_matches_live_nominal_and_manual_states(self):
        check=json.loads((REF/'tube-cutoff-class-check.json').read_text())
        row=self.by_id['B31G22.grid2_mu']
        nominal=electrothermal.parameters()['grid2_mu']
        self.assertEqual(row['value'],nominal)
        self.assertEqual(row['bounds'],list(electrothermal.BOUNDS['grid2_mu'][1:3]))
        self.assertEqual(check['active_model']['nominal_grid2_mu'],nominal)
        self.assertEqual(check['active_model']['sha256'],hashlib.sha256(
            (ROOT/'electrothermal.py').read_bytes()).hexdigest())
        self.assertEqual(check['sources']['tungsram']['pdf_sha256'],
                         self.register['sources']['tungsram_m31_120_1976']['sha256'])
        manual=next(row for row in json.loads((ROOT/'sources.json').read_text())['sources']
                    if row['file']=='older-operation.pdf')
        self.assertEqual(check['sources']['robotron_manual']['pdf_sha256'],
                         manual['sha256'])
        self.assertFalse(check['sources']['tungsram']['exact_installed_type'])
        self.assertFalse(check['active_model']['g4_modeled'])
        self.assertGreater(check['comparison']['nominal_catalog_grid_cutoff_v'],35)
        self.assertLess(check['comparison']['nominal_catalog_grid_cutoff_v'],69)
        self.assertLessEqual(check['comparison']['nominal_dark_drive_v'],0)
        self.assertGreater(check['comparison']['nominal_bright_drive_v'],0)


if __name__ == '__main__':
    unittest.main()
