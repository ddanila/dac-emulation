import copy
import json
import math
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import yoke_geometry as y
import yoke_profile
import trajectory
import trajectory_native
import yoke_axial_geometry_screen as axial

class GeometryTests(unittest.TestCase):
    def test_air_sheet_matches_analytic_field_and_inductance(self):
        c=y.coefficients(2,3,1)
        for a,b in zip(c,(.5,0,.5,0,.5,.5)):self.assertAlmostEqual(a,b,places=12)
        coarse=y.energy_integral(c,2,3,1,128,1000)
        fine=y.energy_integral(c,2,3,1,256,2000)
        self.assertLess(abs(fine-.5),abs(coarse-.5))
        self.assertAlmostEqual(fine,.5,delta=1e-4)

    def test_flux_energy_and_packing(self):
        p=json.loads(y.DEFAULT.read_text());r=y.derive(p)
        self.assertTrue(r['inductance_field_relationship_verified'])
        self.assertFalse(r['specimen_validated'])
        for axis in ('horizontal','vertical'):
            self.assertLess(r['axes'][axis]['energy_flux_relative_error'],.01)
            self.assertLess(r['axes'][axis]['fill_fraction'],p['maximum_fill_fraction'])
            self.assertAlmostEqual(r['electrical'][f'yoke_{axis}_l']/p[axis]['target_inductance_h'],1,delta=.01)
        self.assertEqual(yoke_profile.read(y.DEFAULT),r)
        bad=copy.deepcopy(p);bad['horizontal']['winding_thickness_m']=.0001
        with self.assertRaisesRegex(ValueError,'fill'):y.derive(bad)
        bad=copy.deepcopy(p);bad['horizontal']['sheet_radius_m']=.009
        with self.assertRaisesRegex(ValueError,'clear'):y.derive(bad)
        bad=copy.deepcopy(p);bad['vertical']['sheet_radius_m']=.016
        with self.assertRaises(ValueError):y.derive(bad)

    def test_110_degree_catalog_winding_sensitivity_is_representable(self):
        p=json.loads(y.DEFAULT.read_text())
        p['neck_radius_m']=.009
        p['field_length_m']=.02
        p['horizontal']['target_inductance_h']=.000228
        p['horizontal']['target_resistance_ohm']=.41
        p['vertical']['target_inductance_h']=.00918
        p['vertical']['target_resistance_ohm']=10.2
        derived=y.derive(p)
        self.assertAlmostEqual(derived['electrical']['yoke_horizontal_l'],.000228,delta=.00000228)
        self.assertLess(derived['axes']['horizontal']['fill_fraction'],p['maximum_fill_fraction'])
        trial=axial.trial(p,.23,.02,horizontal_winding=(.000228,.41))
        self.assertAlmostEqual(trial['horizontal_inductance_h'],.000228,delta=.00000228)
        self.assertEqual(trial['horizontal_resistance_ohm'],.41)

    def test_geometry_electrical_override_is_refused(self):
        import steady_supply,transformer_candidates
        r=y.read()
        assembly=dict(yoke=r,components=[],models=[],parameters={k:v[0] for k,v in steady_supply.signal_path.BOUNDS.items()}|r['electrical'])
        selection=dict(status='complete',clock_hz=1000000,period_ticks=19500,
                       events=[[0,0,1,0],[19500,0,1,0]])
        graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
        candidate=transformer_candidates.enumerate_candidates(graph)[0]
        text,metadata=steady_supply.deck(assembly,selection,candidate)
        self.assertEqual(metadata['yoke'],r)
        self.assertEqual(len(metadata['experiment']['sha256']),64)
        assembly['parameters']['yoke_horizontal_l']=.004
        with self.assertRaisesRegex(ValueError,'cannot be overridden'):
            steady_supply.deck(assembly,selection,candidate)

    def test_same_derived_field_in_python_and_compiled_rays(self):
        field=y.read()['field'];native=trajectory_native.Backend()
        for ih,iv in ((.01,0),(0,.01),(-.01,.01)):
            a=trajectory.ray(11000,350,175,ih,iv,overrides=field)
            b=native.ray(11000,350,175,ih,iv,overrides=field)
            self.assertEqual(a['reason'],b['reason'])
            self.assertTrue(a['landed'])
            self.assertAlmostEqual(a['x_m'],b['x_m'],places=11)
            self.assertAlmostEqual(a['y_m'],b['y_m'],places=11)

if __name__=='__main__':unittest.main()
