import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from i8282_propagation_probe import cases as baseline_cases
from i8282_slew_probe import HERE,budgets,cases,verify,voltage

class I8282SlewTests(unittest.TestCase):
    def test_zero_ramps_reproduce_prior_measurements(self):
        rows=list(cases());self.assertEqual(len(rows),144)
        for c,b in zip((c for c in rows if not c['rampSeconds']),baseline_cases()):
            self.assertAlmostEqual(c['crossings']['propagation'],b['stageDelaySeconds'],places=20)
            self.assertAlmostEqual(c['edgeSeconds'],b['expectedSeconds'],places=20)
            self.assertEqual(c['edgePassed'],b['withinPublishedLimit'])

    def test_solution_satisfies_loaded_ode(self):
        load=json.loads((HERE/'bus_switching_limits.json').read_text())['switchingLoad']
        for c in cases():
            if not c['rampSeconds']:continue
            self.assertAlmostEqual(voltage(c,0),c['initialVolts'],places=14)
            for t in (c['rampSeconds']*.4,c['rampSeconds']*1.4):
                h=1e-13;dv=(voltage(c,t+h)-voltage(c,t-h))/(2*h)
                drive=c['startDriveVolts']+(c['driveVolts']-c['startDriveVolts'])*min(t/c['rampSeconds'],1)
                v=voltage(c,t);cap=load['capacitanceFarads']+c['extraCapacitancePf']*1e-12
                expected=((drive-v)/c['resistanceOhms']+(load['biasVolts']-v)/load['resistanceOhms'])/cap
                self.assertTrue(math.isclose(dv,expected,rel_tol=1e-7,abs_tol=.01))
            t=c['rampSeconds']
            self.assertLess(abs(voltage(c,t+1e-16)-voltage(c,t-1e-16)),1e-7)

    def test_edge_rejection_survives_positive_delay_headroom(self):
        groups=budgets(list(cases()))
        def group(r,ramp):return next(g for g in groups if g['highOhms']==r and g['extraCapacitancePf']==0 and g['rampSeconds']==ramp)
        self.assertIsNotNone(group(250,0)['dataDelayIntervalSeconds'])
        self.assertIsNone(group(250,10e-9)['dataDelayIntervalSeconds'])
        self.assertIsNotNone(group(125,10e-9)['dataDelayIntervalSeconds'])
        rejected=group(125,30e-9)
        self.assertGreater(rejected['dataHeadroomSeconds'],0)
        self.assertIsNone(rejected['dataDelayIntervalSeconds'])

    def test_reviewer_refuses_forged_feasible_interval(self):
        source=HERE/'reports/i8282-slew-candidates';verify(source)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';shutil.copytree(source,out)
            path=out/'assessment.json';report=json.loads(path.read_text())
            rejected=next(g for g in report['jointBudgets'] if g['dataDelayIntervalSeconds'] is None)
            rejected['dataDelayIntervalSeconds']=[0,1e-9];path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):verify(out)

if __name__=='__main__':unittest.main()
