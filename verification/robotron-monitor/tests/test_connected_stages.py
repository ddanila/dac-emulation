import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import reference

class ConnectedStagesTests(unittest.TestCase):
    def solve(self,root,name,profile,stop,step,changes=None):
        profile=ROOT/'profiles'/profile;out=root/name
        report=reference.run(profile,out,stop=stop,step=step,changes=changes)
        rows=reference.read_samples(out/'samples.txt',report['probes'],0,stop,step)
        return report,rows

    def test_connected_filter_lock_refinement_and_sync_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            report,base=self.solve(root,'base','k7222-11-vertical-sync.json',.16,2e-6)
            _,fine=self.solve(root,'fine','k7222-11-vertical-sync.json',.16,1e-6)
            _,lost=self.solve(root,'lost','k7222-11-vertical-sync.json',.30,2e-6,
                               {'sync_loss_start':.09,'sync_loss_end':.15})
            def edges(rows):return [b[0] for a,b in zip(rows,rows[1:]) if a[0]>.07 and a[4]<5<=b[4]]
            a,b=edges(base),edges(fine)
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b):self.assertAlmostEqual(x,y,delta=4e-6)
            for x,y in zip(a,a[1:]):self.assertAlmostEqual(y-x,.0208,delta=4e-6)
            e=edges(lost);periods=[(x,y-x) for x,y in zip(e,e[1:])]
            self.assertTrue(any(.10<x<.14 and abs(period-.0208)>.001 for x,period in periods))
            self.assertAlmostEqual(e[-1]-e[-2],.0208,delta=4e-6)
            self.assertEqual(len(report['components']),18)
            self.assertEqual(sum(c['source_id']=='012-6931:C12' for c in report['components']),1)
            deck=(root/'base/run.cir').read_text()
            self.assertNotIn('Ctrigger ',deck)
            self.assertNotIn('vertical_load',deck)
            self.assertFalse(report['coverage']['full_monitor_qualified'])

    def test_regulator_loading_refinement_and_input_sensitivity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            report,rows=self.solve(root,'base','k7222-11-regulator5.json',.30,5e-6)
            _,fine=self.solve(root,'fine','k7222-11-regulator5.json',.30,2.5e-6)
            _,low=self.solve(root,'low','k7222-11-regulator5.json',.30,5e-6,{'reg5_input':6})
            at=lambda rr,t:min(rr,key=lambda r:abs(r[0]-t))
            for t in (.099,.199,.299):
                a,b=at(rows,t),at(fine,t)
                self.assertGreater(a[4],4.8);self.assertLess(a[4],5.3)
                self.assertAlmostEqual(a[4],b[4],delta=.005)
            self.assertLess(at(rows,.199)[4],at(rows,.099)[4])
            self.assertAlmostEqual(at(rows,.099)[4],at(rows,.299)[4],delta=.005)
            self.assertLess(at(low,.199)[4],at(rows,.199)[4]-.2)
            self.assertEqual(len(report['components']),7)
            parts={c['source_id']:c for c in report['components']}
            self.assertEqual(parts['012-6931:C5']['nodes'],['p5','0'])
            self.assertEqual(float(parts['012-6931:C5']['value']),.001)
            self.assertNotIn('012-6931:C8',parts)
            self.assertFalse(report['coverage']['full_monitor_qualified'])

    def test_multisheet_duplicate_source_rejected_before_solve(self):
        profile=json.loads((ROOT/'profiles/k7222-11-vertical-sync.json').read_text())
        # A repeated sheet is a duplicated electrical component, not extra coverage.
        profile['additional_schematics'].append(profile['additional_schematics'][0])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'profile.json';p.write_text(json.dumps(profile))
            with self.assertRaises(ValueError):reference.read_profile(p)

if __name__=='__main__':unittest.main()
