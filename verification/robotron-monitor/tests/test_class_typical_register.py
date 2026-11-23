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
import tube_heater_class_check


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

    def test_yoke_class_report_tracks_active_design_and_source(self):
        report = json.loads((REF/'yoke-class-comparator.json').read_text())
        self.assertEqual(report['source']['sha256'],
                         self.register['sources']['philips_t16_yoke_class']['sha256'])
        for key, path in (('profile', ROOT/'profiles/k7222-11-yoke-geometry.json'),
                          ('targets', REF/'service-observations.json'),
                          ('design', REF/'design-point.json')):
            self.assertEqual(report['inputs_sha256'][key],
                             hashlib.sha256(path.read_bytes()).hexdigest())
        class_bounds = report['class_envelope_si']
        for id_suffix, key in (('line_inductance', 'line_inductance_h'),
                               ('line_resistance', 'line_resistance_ohm'),
                               ('field_inductance', 'field_inductance_h'),
                               ('field_resistance', 'field_resistance_ohm')):
            self.assertEqual(self.by_id['AE9VT.class_'+id_suffix]['bounds'],
                             class_bounds[key])
        current = report['conditional_current_proxy']
        for axis in ('line', 'field'):
            row = self.by_id['AE9VT.class_'+axis+'_current_proxy']
            self.assertEqual(row['value'], current[axis+'_nominal_at1077_05_app'])
            self.assertEqual(row['bounds'], current[axis+'_family_envelope_app'])
        trials = report['class_winding_geometry_trials']
        self.assertFalse(trials[0]['reaches_target'])
        self.assertTrue(trials[1]['reaches_target'])
        self.assertLess(trials[1]['neck_clip_current_margin_fraction'], .01)

    def test_brimar_110deg_pair_and_conditional_stage_have_provenance(self):
        report = json.loads((REF/'yoke-brimar-110deg-comparator.json').read_text())
        stage = json.loads((REF/'t3-yoke-brimar-stage-screen.json').read_text())
        self.assertEqual(report['source']['sha256'],
                         self.register['sources']['brimar_tby_110deg_20mm']['sha256'])
        self.assertEqual(stage['source']['sha256'], report['source']['sha256'])
        for name, path in (('target', REF/'yoke-class-comparator.json'),
                           ('script', ROOT/'yoke_brimar_110deg_comparator.py')):
            self.assertEqual(report['input_hashes'][name], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(stage['inputs_sha256']['reference/k7222-11/yoke-brimar-110deg-comparator.json'],
                         hashlib.sha256((REF/'yoke-brimar-110deg-comparator.json').read_bytes()).hexdigest())
        cases = {row['type']: row for row in report['class_cases']}
        self.assertEqual(set(cases), {'TBY3', 'TBY5', 'TBY7'})
        self.assertEqual((cases['TBY7']['line_inductance_h'],
                          cases['TBY7']['line_resistance_ohm'],
                          cases['TBY7']['field_inductance_h'],
                          cases['TBY7']['field_resistance_ohm']), (.0041, 8.8, .032, 16))
        for suffix, key in (('line_inductance', 'line_inductance_h'),
                            ('line_resistance', 'line_resistance_ohm'),
                            ('field_inductance', 'field_inductance_h'),
                            ('field_resistance', 'field_resistance_ohm')):
            self.assertEqual(self.by_id['AE9VT.TBY7_candidate_'+suffix]['value'],
                             cases['TBY7'][key])
        stage_cases = {row['catalog_type']: row for row in stage['class_cases']}
        self.assertEqual(set(stage_cases), set(cases))
        self.assertEqual(stage['class_cases_in_11_12kv_band_at_collector_peak'], 0)
        self.assertTrue(2000 < stage_cases['TBY7']['eht_at_collector_peak_v'] < 3000)
        self.assertLess(stage_cases['TBY3']['eht_at_collector_peak_v'],
                        stage_cases['TBY7']['eht_at_collector_peak_v'])

    def test_tube_heater_class_point_matches_live_equilibrium(self):
        check=json.loads((REF/'tube-heater-class-check.json').read_text())
        self.assertEqual(check['format'],'dac-monitor-tube-heater-class-check-v2')
        source=self.register['sources']['tungsram_m31_120_1976']
        self.assertEqual(source['sha256'],check['source']['pdf_sha256'])
        tungsten=self.register['sources']['nasa_tungsten_material_handbook']
        self.assertEqual(tungsten['sha256'],check['tungsten_source']['pdf_sha256'])
        self.assertFalse(check['comparator']['exact_installed_type'])
        row=self.by_id['B31G22.heater_effective_hot_resistance']
        nominal=electrothermal.parameters()
        rise=steady_supply.heater_equilibrium()['temperature_rise_k'][0]
        hot=nominal['heater_cold_ohm']*(1+nominal['heater_alpha']*rise)
        self.assertAlmostEqual(row['value'],hot,places=9)
        self.assertEqual(row['bounds'],[check['assumed_class_spread']['scenarios'][0]['hot_resistance_ohm'],
                                        check['assumed_class_spread']['scenarios'][-1]['hot_resistance_ohm']])
        self.assertLess(abs(check['comparison']['heater_current_relative_error']),.02)
        for key, model_key in (('heater_cold_resistance','heater_cold_ohm'),
                               ('heater_linear_alpha','heater_alpha')):
            row=self.by_id['B31G22.'+key]
            self.assertEqual(row['value'],nominal[model_key])
            self.assertEqual(row['bounds'],list(electrothermal.BOUNDS[model_key][1:3]))
            self.assertIn('nasa_tungsten_material_handbook',row['sources'])
        rho=check['tungsten_source']['resistivity_micro_ohm_m']
        for temperature in ('1000','1200','1400'):
            ratio=rho[temperature]/rho['300']
            self.assertAlmostEqual(check['cold_resistance_proxy']['ratios_to_300k'][temperature],ratio)
        reported=check['cold_resistance_proxy']['nominal_branch']
        actual=tube_heater_class_check.branch_equilibrium(
            nominal['heater_cold_ohm'],nominal['heater_alpha'])
        self.assertAlmostEqual(actual['heater_current_a'],reported['heater_current_a'],places=12)
        self.assertEqual(len(check['cold_resistance_proxy']['joint_bound_corners']),4)

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
