import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import atlas
import atlas_features as features
import faults
import magnetics
import reference


class MutationTests(unittest.TestCase):
    def setUp(self):
        self.parts=[dict(reference='C1',nodes=['rail','0'],value='22u',source_id='board:C1'),
                    dict(reference='Q1',nodes=['c','b','0'],value='N',source_id='board:V1')]
        self.models='.model N NPN(IS=1e-14 BF={gain} CJE=20p)\n'

    def test_mutations_are_isolated_and_preserve_identity(self):
        original=copy.deepcopy(self.parts)
        for fault in [dict(target='board:C1',operation='esr',resistance_ohm=10),
                      dict(target='board:C1',operation='capacitance_scale',factor=.1),
                      dict(target='board:V1',operation='open',terminal=2),
                      dict(target='board:V1',operation='short',terminals=[1,3]),
                      dict(target='board:V1',operation='leakage',terminals=[1,3],resistance_ohm=1e6)]:
            changed,_,record=faults.apply(self.parts,self.models,fault)
            self.assertEqual(self.parts,original)
            self.assertEqual(record['original']['source_id'],fault['target'])
            self.assertEqual(sum(c.get('source_id')==fault['target'] for c in changed),1)
            for item in record['inserted']:self.assertEqual(item['derived_from'],fault['target'])

    def test_gain_fault_is_per_device_and_cannot_widen_healthy_range(self):
        changed,models,record=faults.apply(self.parts,self.models,dict(target='board:V1',operation='gain_scale',factor=.1))
        self.assertIn('BF={(gain)*0.1}',models)
        self.assertEqual(changed[1]['value'],'FAULT_Q1')
        self.assertIn('.model N NPN(IS=1e-14 BF={gain}',models)
        profile=reference.read_profile(ROOT/'profiles/k7222-11-neck-diagnostic.json')
        with self.assertRaises(ValueError):reference.parameter_values(profile,{'q_bf':1})

    def test_invalid_and_unsupported_mutations_fail_closed(self):
        for fault in [dict(target='missing',operation='open'),dict(target='board:C1',operation='gain_scale',factor=.1),
                      dict(target='board:C1',operation='short',terminals=[1,3]),
                      dict(target='board:C1',operation='capacitance_scale',factor=float('nan'))]:
            with self.assertRaises(ValueError):faults.apply(self.parts,self.models,fault)
        self.assertEqual(faults.number('1M'),.001)
        self.assertEqual(faults.number('1meg'),1e6)

    def test_same_capacitor_joint_degradation_retains_healthy_esr(self):
        parts=faults.parasitics(self.parts,[dict(target='board:C1',parameter='esr')],{'esr':.3})
        self.assertEqual(self.parts[0]['nodes'],['rail','0'])
        matrix=faults.capacitor_matrix('board:C1')
        self.assertEqual(len(matrix),15)
        self.assertEqual(len({f['id'] for f in matrix}),15)
        for fault in matrix:
            c_factor,esr_factor=fault['capacitance_factor'],fault['esr_factor']
            changed,_,record=faults.apply(parts,self.models,fault)
            self.assertAlmostEqual(float(changed[0]['value']),22e-6*c_factor)
            losses=[c for c in changed if c.get('derived_from')=='board:C1']
            self.assertAlmostEqual(sum(float(c['value']) for c in losses),.3*esr_factor)
            self.assertEqual(record['original']['source_id'],'board:C1')
            self.assertEqual(float(parts[-1]['value']),.3)
        with self.assertRaises(faults.UnsupportedFault):
            faults.apply(self.parts,self.models,dict(target='board:C1',operation='capacitor_degradation',esr_factor=3))
        for target in ('missing','board:V1'):
            with self.assertRaises(ValueError):
                faults.parasitics(self.parts,[dict(target=target,parameter='esr')],{'esr':.3})


class FeatureTests(unittest.TestCase):
    def test_time_weighted_metrics_and_ambiguity(self):
        probe=[dict(id='board:node:V',unit='V')]
        f=features.extract([[0,0],[.1,.1],[1,1]],probe,[dict(id='ramp',start=0,stop=1)])
        self.assertAlmostEqual(f['board:node:V|ramp|mean']['value'],.5)
        self.assertAlmostEqual(f['board:node:V|ramp|rms']['value'],math.sqrt(1/3))
        env=features.envelope([f]);self.assertTrue(features.compare(env,env)['ambiguous'])
        shifted=copy.deepcopy(f)
        for v in shifted.values():v['value']+=10
        self.assertFalse(features.compare(env,features.envelope([shifted]))['ambiguous'])
        self.assertFalse(features.refinement(f,shifted)['passed'])

    def test_joint_sampling_is_reproducible_bounded_and_separate_from_holdout(self):
        cat,scenario,profile,_=atlas.load_inputs(ROOT/'atlas/catalogue.json',ROOT/'atlas/scenarios.json','nominal')
        inventory=json.loads((ROOT/profile['inventory']).read_text())
        a=atlas.ensemble(profile,inventory,8,7,scenario)
        self.assertEqual(a,atlas.ensemble(profile,inventory,8,7,scenario))
        self.assertNotEqual(a,atlas.ensemble(profile,inventory,8,8,scenario))
        for sample in a:reference.parameter_values(profile,sample['parameters'])
        self.assertTrue(a[0]['component_factors'])


class MagneticTests(unittest.TestCase):
    def setUp(self):
        self.core=dict(area_m2=1e-4,length_m=.05,loss_ohm=10000,
                       h_a_per_m=[-100000,-1000,-200,0,200,1000,100000],b_t=[-.5,-.3,-.2,0,.2,.3,.5])
        self.windings=[dict(turns=n,resistance_ohm=.1,leakage_h=1e-6,capacitance_f=10e-12) for n in (20,40)]

    def solve(self,directory,fault=None,step=1e-6,voltage=1):
        directory.mkdir()
        model=magnetics.transformer('shared',self.windings,self.core,fault)
        deck=f'''Magnetic validation block, not historical transformer
Vinput input 0 SIN(0 {voltage} 1000)
Rsource input pri 1
Xcore pri 0 sec 0 shared
Rload sec 0 1000
{model}
.options reltol=1e-5
.control
set wr_singlescale
set wr_vecnames
set numdgt=15
tran {step} .005 0 {step/5}
linearize v(input) v(sec) i(vinput)
wrdata samples.txt v(input) v(sec) i(vinput)
quit
.endc
.end
'''
        (directory/'run.cir').write_text(deck)
        reference.lab.run_command(['ngspice','-b','run.cir'],directory,directory/'log.txt')
        return reference.read_samples(directory/'samples.txt',[{},{},{}],0,.005,step)

    def test_energy_polarity_short_turn_and_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            a=self.solve(p/'nominal')
            b=self.solve(p/'shorted',dict(turns=2,resistance_ohm=.05,leakage_h=1e-8))
            c=self.solve(p/'refined',step=.5e-6)
            def energy(rows,col):
                return sum((y[0]-x[0])*(col(x)+col(y))/2 for x,y in zip(rows,rows[1:]))
            input_j=energy(a,lambda r:-r[1]*r[3]);output_j=energy(a,lambda r:r[2]**2/1000)
            self.assertGreater(input_j,0);self.assertLess(output_j,input_j*1.01)
            self.assertGreater(sum(r[1]*r[2] for r in a),0)
            self.assertLess(max(r[2] for r in b),max(r[2] for r in a))
            self.assertGreater(energy(b,lambda r:-r[1]*r[3]),input_j)
            self.assertAlmostEqual(energy(c,lambda r:r[2]**2/1000),output_j,delta=output_j*.01)
            saturated=self.solve(p/'saturated',voltage=10)
            rms=lambda rows: math.sqrt(sum(r[3]**2 for r in rows)/len(rows))
            self.assertGreater(rms(saturated),rms(a)*12)

    def test_nonpassive_core_and_invalid_windings_rejected(self):
        self.core['b_t'][4]=-.1
        with self.assertRaises(ValueError):magnetics.transformer('bad',self.windings,self.core)


if __name__=='__main__':unittest.main()
