import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import transformer_candidates as tc
import reference,lab

class TransformerCandidateTests(unittest.TestCase):
    def setUp(self):
        self.graph=json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())

    def test_hypotheses_are_explicit_unique_and_global_reversal_is_equivalent(self):
        candidates=tc.enumerate_candidates(self.graph)
        self.assertEqual(len(candidates),16)
        self.assertEqual(len({c['id'] for c in candidates}),16)
        for c in candidates:
            self.assertFalse(c['historical_topology_verified'])
            reversed_signs={k:-v for k,v in c['polarity'].items()}
            self.assertEqual(tc.signature(self.graph,reversed_signs),c['topology_sha256'])
        broken=copy.deepcopy(self.graph);broken['groups'][0]['taps'][1]=broken['groups'][0]['taps'][0]
        with self.assertRaises(ValueError):tc.enumerate_candidates(broken)
        with self.assertRaises(ValueError):tc.compile_model(self.graph,candidates[0],{})

    def test_taps_polarity_and_loading_use_shared_core(self):
        graph=copy.deepcopy(self.graph);graph['groups']=graph['groups'][:1]+graph['groups'][2:3]
        graph['groups'][0]['taps']=['X2_7','X2_10','X2_4']
        def bound(v):return dict(value=v,minimum=v/2,maximum=v*2,evidence='assumed-bound',rationale='Synthetic transformer unit-test parameter, not a T3 estimate.')
        def section(turns):return {k:bound(v) for k,v in dict(turns=turns,resistance_ohm=.1,leakage_h=1e-6,capacitance_f=10e-12).items()}
        params=dict(format='dac-monitor-magnetic-parameters-v1',rationale='Synthetic tapped transformer test only',groups=dict(drive=[section(20),section(20)],high_voltage=[section(80)]),core=dict(area_m2=bound(1e-4),length_m=bound(.05),loss_ohm=bound(10000),h_a_per_m=[-100000,-1000,-200,0,200,1000,100000],b_t=[-.5,-.3,-.2,0,.2,.3,.5]))
        candidates=tc.enumerate_candidates(graph)
        with tempfile.TemporaryDirectory() as tmp:
            def solve(name,candidate,load=1000):
                out=Path(tmp)/name;out.mkdir()
                model,report=tc.compile_model(graph,candidate,params)
                self.assertFalse(report['full_monitor_qualified'])
                profile=dict(name='Tapped magnetic test',probes=[dict(expression=e) for e in ('v(pri)','v(tap)','v(sec)','i(Vsource)')])
                bench=f'Vsource source 0 SIN(0 1 1000)\nRsource source pri 1\nXcore pri tap 0 sec 0 T3_CANDIDATE\nRload sec 0 {load}\n'
                (out/'run.cir').write_text(reference.deck(profile,[],{},0,.005,1e-6,model,bench))
                lab.run_command(['ngspice','-b','run.cir'],out,out/'solver.log')
                return reference.read_samples(out/'samples.txt',profile['probes'],0,.005,1e-6)
            normal=solve('normal',candidates[0]);opposite=solve('opposite',candidates[1]);loaded=solve('loaded',candidates[0],10)
            selected=[r for r in normal if r[0]>.003]
            gain=lambda rows,col:sum(r[1]*r[col] for r in rows)/sum(r[1]**2 for r in rows)
            self.assertAlmostEqual(gain(selected,2),.5,delta=.02)
            self.assertAlmostEqual(gain(selected,3),2,delta=.03)
            self.assertLess(gain(opposite,3),-1.9)
            self.assertGreater(sum(r[4]**2 for r in loaded),sum(r[4]**2 for r in normal)*2)
        broken=copy.deepcopy(params);broken['groups']['drive'][0]['turns']['value']=0
        with self.assertRaises(ValueError):tc.compile_model(graph,candidates[0],broken)

if __name__=='__main__':unittest.main()
