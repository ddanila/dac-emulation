"""Connected pulse-to-ramp behavior; these are not full-monitor assertions."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import reference

class VerticalIntegratorTests(unittest.TestCase):
    def test_ramp_reset_trim_and_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=ROOT/'profiles/k7222-11-vertical-integrator.json'
            def solve(name,step,changes=None):
                report=reference.run(profile,root/name,stop=.16,step=step,changes=changes)
                return report,reference.read_samples(root/name/'samples.txt',report['probes'],0,.16,step)
            report,base=solve('base',4e-6)
            _,fine=solve('fine',2e-6)
            _,trim=solve('trim',4e-6,{'height_trim':22000})
            _,comp=solve('comp',4e-6,{'vertical_compensation':1e-9})
            at=lambda rr,t:min(rr,key=lambda r:abs(r[0]-t))
            # Linear charging over the field; a short active reset, not a
            # precomputed PWL/sawtooth source, creates the falling edge.
            values=[at(base,t)[8] for t in (.107,.111,.115,.119,.123)]
            slopes=[(b-a)/.004 for a,b in zip(values,values[1:])]
            self.assertGreater(min(slopes),50)
            self.assertLess(max(slopes)/min(slopes),1.05)
            resets=[b[0] for a,b in zip(base,base[1:]) if a[0]>.07 and a[8]>.5>=b[8]]
            self.assertGreaterEqual(len(resets),3)
            for a,b in zip(resets,resets[1:]):self.assertAlmostEqual(b-a,.0208,delta=8e-6)
            for t in (.107,.111,.115,.119,.123,.145,.149):
                self.assertAlmostEqual(at(base,t)[8],at(fine,t)[8],delta=.01)
                self.assertAlmostEqual(at(base,t)[8],at(comp,t)[8],delta=.02)
            self.assertLess(at(trim,.119)[8],at(base,.119)[8]*.95)
            self.assertEqual(report['coverage']['connected'],34)
            self.assertFalse(report['coverage']['full_monitor_qualified'])
            parts={p['source_id']:p for p in report['components']}
            self.assertEqual(parts['012-6931:V13']['nodes'],['ramp_inv','retrace_base','ramp_bias'])
            self.assertEqual(parts['012-6931:V12']['nodes'],['ramp_noninv','vertical_pulse'])
            inventory=json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
            c15=next(p for p in inventory['parts'] if p['id']=='012-6931:C15')
            self.assertIsNone(c15['value']);self.assertEqual(c15['evidence'],'unresolved')

if __name__=='__main__':unittest.main()
