"""Independent terminal-power and cross-backend checks, not T1 qualification."""
import copy
from functools import partial
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import converter_magnetics
import lab
import magnetics
import reference


class FluxTests(unittest.TestCase):
    def solve(self, backend=magnetics.transformer_flux, *, polarity=1, load=100,
              step=1e-6, amplitude=1, short=None):
        windings = [dict(turns=n, resistance_ohm=.1, leakage_h=1e-6,
                         capacitance_f=1e-11, polarity=s) for n, s in ((40, 1), (80, polarity))]
        core = dict(area_m2=1e-4, length_m=.05, loss_ohm=10000,
                    h_a_per_m=[-100000, -1000, -200, 0, 200, 1000, 100000],
                    b_t=[-.5, -.3, -.2, 0, .2, .3, .5])
        model = backend('CORE', windings, core, short)
        profile = dict(name='Synthetic magnetic test', probes=[dict(expression=e)
            for e in ('v(pri)', 'v(sec)', 'i(Vsource)')])
        bench = (f'Vsource source 0 SIN(0 {amplitude} 1000)\nRsource source pri 1\n'
                 f'Xcore pri 0 sec 0 CORE\nRload sec 0 {load}\n')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'run.cir').write_text(reference.deck(profile, [], {}, 0, .01, step, model, bench))
            log = lab.run_command(['ngspice', '-b', 'run.cir'], out, out/'solver.log')
            self.assertIsNone(re.search(r'error|aborted|timestep too small|singular matrix', log, re.I), log)
            rows = reference.read_samples(out/'samples.txt', profile['probes'], 0, .01, step)
        rows = [r for r in rows if .008 <= r[0] < .01]
        gain = sum(r[1]*r[2] for r in rows)/sum(r[1]**2 for r in rows)
        rms = math.sqrt(sum(r[3]**2 for r in rows)/len(rows))
        supplied = sum(-amplitude*math.sin(2*math.pi*1000*r[0])*r[3] for r in rows)*step
        delivered = sum(r[2]**2/load for r in rows)*step
        # Periodic stored energy does not grow; the network cannot create power.
        self.assertGreater(supplied, delivered*.999)
        self.assertGreater(delivered, 0)
        return gain, rms, supplied, delivered

    def test_shared_flux_matches_xspice_and_timestep_refinement(self):
        normal = self.solve()
        old = self.solve(magnetics.transformer)
        refined = self.solve(step=5e-7)
        twice = self.solve(step=2.5e-7)
        self.assertAlmostEqual(normal[0], 2, delta=.02)
        for result in (old, refined, twice):
            for a, b in zip(normal, result):
                self.assertAlmostEqual(a, b, delta=abs(a)*.005)
        self.assertGreater(normal[3]/normal[2], .85)

    def test_polarity_loading_short_and_saturation(self):
        normal = self.solve()
        reverse = self.solve(polarity=-1)
        loaded = self.solve(load=10)
        shorted = self.solve(short=dict(turns=2, resistance_ohm=.02, leakage_h=1e-8))
        saturated = self.solve(amplitude=20)
        saturated_refined = self.solve(amplitude=20, step=5e-7)
        saturated_smooth = self.solve(partial(magnetics.transformer_flux, smoothing_t=5e-6), amplitude=20)
        self.assertAlmostEqual(reverse[0], -normal[0], delta=.001)
        self.assertAlmostEqual(reverse[1], normal[1], delta=normal[1]*.001)
        self.assertGreater(loaded[1], normal[1]*2)
        self.assertGreater(shorted[1], normal[1]*2)
        self.assertGreater(saturated[1], normal[1]*20)
        for result in (saturated_refined, saturated_smooth):
            for a, b in zip(saturated, result):
                self.assertAlmostEqual(a, b, delta=abs(a)*.01)

    def test_t1_generation_bounds_and_profile_contract(self):
        parameters = json.loads((ROOT/'devices/t1-bound.json').read_text())
        self.assertEqual(converter_magnetics.compile_model(parameters), (ROOT/'devices/t1-bound.cir').read_text())
        reference.read_profile(ROOT/'profiles/k7222-11-converter.json')
        for key in ('turns', 'leakage_h', 'capacitance_f', 'resistance_ohm'):
            invalid = copy.deepcopy(parameters)
            invalid['windings'][0][key]['value'] = 0
            with self.assertRaises(ValueError): converter_magnetics.compile_model(invalid)
        invalid = copy.deepcopy(parameters); invalid['historical_topology_verified'] = True
        with self.assertRaises(ValueError): converter_magnetics.compile_model(invalid)
        invalid = copy.deepcopy(parameters); invalid['core']['b_scale']['value'] = 3
        with self.assertRaises(ValueError): converter_magnetics.compile_model(invalid)


if __name__ == '__main__': unittest.main()
