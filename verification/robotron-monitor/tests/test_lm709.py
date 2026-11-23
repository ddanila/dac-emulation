"""Behavioral checks for a manufacturer-topology, uncalibrated family model."""
from pathlib import Path
import json,re,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import lab,lm709_dc_check,reference

class LM709Tests(unittest.TestCase):
    def test_saved_dc_follower_diagnostic(self):
        saved = lm709_dc_check.run()
        self.assertEqual([row['input_v'] for row in saved['cases']],[-1,0,1])

    def solve(self,comp=5e-9,step=1e-7,load=10000):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            p=dict(name='LM709 compensated follower',subcircuits={'LM709_FAMILY':8},
                   probes=[dict(expression=e) for e in ('v(input)','v(output)','i(Vp)','i(Vm)')])
            bench=f'''Vp vp 0 15
Vm vm 0 -15
Vi input 0 PULSE(-1 1 10u 1u 1u 40u 80u)
Xamp ca output input vm co raw vp cb LM709_FAMILY
C1 ca comp {comp}
R1 comp cb 1.5k
C2 co raw 200p
R2 raw output 51
Rl output 0 {load}
'''
            (out/'run.cir').write_text(reference.deck(p,[],{},0,100e-6,step,
                (ROOT/'devices/lm709-family.cir').read_text(),bench))
            log=lab.run_command(['ngspice','-b','run.cir'],out,out/'ngspice.log')
            self.assertIsNone(re.search(r'error|warning|timestep too small|singular matrix',log,re.I),log)
            return reference.read_samples(out/'samples.txt',p['probes'],0,100e-6,step)

    def test_compensation_load_and_refinement(self):
        base=self.solve();fine=self.solve(step=5e-8);slow=self.solve(comp=20e-9);loaded=self.solve(load=2000)
        at=lambda rows,t:min(rows,key=lambda r:abs(r[0]-t))
        for t in (5e-6,35e-6,75e-6):
            a=at(base,t)
            self.assertAlmostEqual(a[1],a[2],delta=.003)
            self.assertAlmostEqual(a[2],at(fine,t)[2],delta=.001)
            self.assertAlmostEqual(a[2],at(loaded,t)[2],delta=.005)
            self.assertTrue(.001 < -a[3] < .01)
            self.assertTrue(.001 < a[4] < .01)
            # KCL includes input bias and load; no hidden ideal output supply.
            self.assertAlmostEqual(-a[3]-a[4],a[2]/10000,delta=2e-6)
        crossing=lambda rows:next(r[0] for r in rows if r[0]>10e-6 and r[2]>.8)
        self.assertGreater(crossing(slow)-crossing(base),1e-6)
        self.assertAlmostEqual(crossing(base),crossing(fine),delta=2e-7)

if __name__=='__main__':unittest.main()
