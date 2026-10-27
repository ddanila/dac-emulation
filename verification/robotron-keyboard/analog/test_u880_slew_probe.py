import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

from u880_output_probe import cases as instantaneous
from u880_slew_probe import HERE, budgets, cases, crossing, fraction, verify


class CpuSlewTests(unittest.TestCase):
    def test_instantaneous_control_matches_prior_experiment(self):
        prior = list(instantaneous())
        for c in cases():
            if c['edge'] != 'rise' or c['rampSeconds']:
                continue
            original = next(x for x in prior if x['highOhms'] == c['highOhms']
                and x['extraCapacitanceFarads'] == c['extraCapacitanceFarads'] and x['initialVolts'] == 0)
            self.assertAlmostEqual(c['analyticSeconds'], original['analyticSeconds'], places=20)

    def test_ramp_crossings_on_both_sides_of_ramp_end(self):
        tau, ramp = 20e-9, 60e-9
        for target in (.1, .99):
            t = crossing(tau, ramp, target)
            self.assertAlmostEqual(fraction(t, tau, ramp), target)
            self.assertEqual(t < ramp, target == .1)
        self.assertAlmostEqual(fraction(ramp, tau, ramp), 1 - tau / ramp * (1 - math.exp(-ramp/tau)))

    def test_slew_rejects_previously_feasible_combination(self):
        rows = list(cases())
        self.assertEqual(len(rows), 32)
        joint = budgets(rows)
        def row(ramp):
            return next(x for x in joint if x['highOhms'] == 4000.
                and x['extraCapacitanceFarads'] == 1e-11 and x['rampSeconds'] == ramp)
        self.assertGreater(row(0.)['internalDelayIntervalSeconds'][1], 19e-9)
        self.assertIsNone(row(60e-9)['internalDelayIntervalSeconds'])
        self.assertTrue(all(c['withinBudget'] for c in rows if c['edge'] == 'fall'))

    def test_replay_rejects_forged_admission_budget(self):
        retained = HERE / 'reports/u880-slew-candidates'
        verify(retained)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'report'
            shutil.copytree(retained, out)
            path = out / 'assessment.json'
            report = json.loads(path.read_text())
            rejected = next(x for x in report['jointDelayBudgets'] if x['internalDelayIntervalSeconds'] is None)
            rejected['internalDelayIntervalSeconds'] = [0., 1e-9]
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                verify(out)


if __name__ == '__main__':
    unittest.main()
