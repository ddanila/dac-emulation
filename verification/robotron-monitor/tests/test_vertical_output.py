"""Current-feedback vertical stage; no full-monitor or specimen claims."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import reference

class VerticalOutputTests(unittest.TestCase):
    def test_current_feedback_refinement_and_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def solve(name,step=10e-6,changes=None):
                r=reference.run(ROOT/'profiles/k7222-11-vertical-output.json',root/name,
                                stop=.16,step=step,changes=changes)
                return r,reference.read_samples(root/name/'samples.txt',r['probes'],0,.16,step)
            report,base=solve('base')
            _,fine=solve('fine',5e-6)
            _,shift=solve('shift',changes={'symmetry_fraction':.9})
            _,trim=solve('height',changes={'height_trim':22000})
            at=lambda rows,t:min(rows,key=lambda r:abs(r[0]-t))
            # Polarity comes from the inverting current amplifier, not a
            # renderer scaling parameter. Actual current crosses zero.
            self.assertGreater(at(base,.107)[13],.15)
            self.assertLess(at(base,.123)[13],-.1)
            for t in (.107,.111,.115,.119,.123,.149):
                a,b=at(base,t),at(fine,t)
                self.assertAlmostEqual(a[13],b[13],delta=.001)
                self.assertAlmostEqual(a[14],b[14],delta=.01)
                self.assertAlmostEqual(a[17],a[18],delta=.001)
                self.assertTrue(16<a[16]<17.5)
                # Independently check solved series R/L winding equation.
                derivative=(at(base,t+1e-5)[13]-at(base,t-1e-5)[13])/2e-5
                self.assertAlmostEqual(a[14]-a[15],10*a[13]+.02*derivative,delta=.015)
            self.assertGreater(at(shift,.119)[13],at(base,.119)[13]+.02)
            span=lambda rows:at(rows,.107)[13]-at(rows,.123)[13]
            self.assertLess(span(trim),span(base)*.95)
            self.assertEqual(report['coverage']['connected'],76)
            self.assertFalse(report['coverage']['full_monitor_qualified'])
            self.assertIn('model_0',report['hashes']);self.assertIn('model_1',report['hashes'])
            self.assertNotIn('Rramp_load',(root/'base/run.cir').read_text())
            parts={p['source_id']:p for p in report['components']}
            self.assertEqual(parts['012-6931:V23']['nodes'],['threshold_lower','threshold_upper'])
            self.assertEqual(parts['012-6931:C23']['nodes'],['vertical_reference','0'])
            self.assertEqual(parts['012-6931:R29']['value'],'430')

    def test_model_paths_are_confined_and_unique(self):
        p=json.loads((ROOT/'profiles/k7222-11-vertical-output.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'profile.json'
            for bad in [['/etc/passwd'],['../outside.cir'],['devices/lm709-family.cir']*2,
                        [p['models']],['circuits/k7222-11-neck.kicad_sch'],None,[3]]:
                p['additional_models']=bad;f.write_text(json.dumps(p))
                with self.assertRaises(ValueError):reference.read_profile(f)

if __name__=='__main__':unittest.main()
