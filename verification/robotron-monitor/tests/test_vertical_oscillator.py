import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import reference,full_path_audit

class VerticalOscillatorTests(unittest.TestCase):
    def test_source_topology_free_running_period_and_refinement(self):
        profile=ROOT/'profiles/k7222-11-vertical-oscillator.json'
        probes=reference.read_profile(profile)['probes']
        with tempfile.TemporaryDirectory() as tmp:
            def solve(name,step,changes=None):
                out=Path(tmp)/name
                report=reference.run(profile,out,stop=.12,step=step,changes=changes)
                rows=reference.read_samples(out/'samples.txt',probes,0,.12,step)
                edges=[b[0] for a,b in zip(rows,rows[1:]) if a[0]>.06 and a[4]<5<=b[4]]
                self.assertGreaterEqual(len(edges),2)
                period=edges[-1]-edges[-2]
                return report,rows,period
            report,rows,period=solve('base',2e-6)
            components={c['source_id']:c for c in report['components']}
            self.assertEqual(len(components),11)
            self.assertEqual(components['012-6931:R32']['nodes'],['vertical_supply','vertical_pulse'])
            self.assertEqual(components['012-6931:R25']['nodes'],['vertical_pulse','vertical_trigger'])
            self.assertEqual(components['012-6931:C13']['nodes'],['vertical_timing','vertical_base'])
            self.assertFalse(report['coverage']['full_monitor_qualified'])
            self.assertGreater(period,.015);self.assertLess(period,.04)
            self.assertGreater(max(r[4] for r in rows if r[0]>.06),10)
            _,_,refined=solve('refined',1e-6)
            self.assertLess(abs(period-refined)/refined,.002)
            _,_,faster=solve('trim',2e-6,{'vertical_trim':1000})
            self.assertLess(faster,period)

    def test_full_path_gate_counts_actual_connectivity(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=full_path_audit.audit(Path(tmp)/'audit')
            self.assertEqual(report['status'],'blocked')
            self.assertEqual(report['coverage']['connected'],247)
            self.assertEqual(len(report['dispositions']),260)
            self.assertEqual(sum(p['disposition']=='modeled' for p in report['dispositions']),247)
            self.assertNotIn('012-6921:T1',report['coverage']['missing'])
            self.assertNotIn('012-6921:T2',report['coverage']['missing'])
            self.assertNotIn('012-6921:T3',report['coverage']['missing'])
            self.assertFalse(report['full_path_render_eligible'])
            self.assertFalse(report['full_monitor_qualified'])

if __name__=='__main__':unittest.main()
