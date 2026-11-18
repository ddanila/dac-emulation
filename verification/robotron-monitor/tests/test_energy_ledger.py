import json,math,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import energy_ledger as energy
import steady_supply

class EnergyTests(unittest.TestCase):
    def test_inverse_core_energy_matches_constitutive_derivative(self):
        core=dict(area_m2=.0001,length_m=.08,h_a_per_m=[-900,-100,0,100,900],b_t=[-.4,-.2,0,.2,.4])
        for b in (.01,.15,.21,.32,-.32):
            derivative=(energy.core_energy(b+1e-7,core)-energy.core_energy(b-1e-7,core))/2e-7
            smooth=1e-5;h=500*b+3500*(b+.5*(math.sqrt((b-.2)**2+smooth**2)-math.sqrt((b+.2)**2+smooth**2)))
            self.assertAlmostEqual(derivative,core['area_m2']*core['length_m']*h,delta=1e-10)
        self.assertAlmostEqual(energy.core_energy(.3,core),energy.core_energy(-.3,core),places=14)

    def test_unsupported_primitive_blocks_inventory(self):
        with self.assertRaisesRegex(ValueError,'unsupported'):energy.inventory(' 1 : title\n 2 : m1 d g s 0 mos\n')
        with self.assertRaisesRegex(ValueError,'empty'):energy.inventory(' 1 : title\n')

    @unittest.skipUnless(Path(os.environ.get('MONITOR_RUNTIME','build/monitor/runtime-clean')).exists(),'pinned runtime required')
    def test_rc_rl_mutual_and_signed_device_work(self):
        runtime=Path(os.environ.get('MONITOR_RUNTIME','build/monitor/runtime-clean')).resolve()
        fixtures={
            'ideal_transformer':'V1 in 0 PWL(0 0 1u 1)\nE1 secondary 0 in 0 .5\nVsense secondary load 0\nR1 load 0 1000\nF1 in 0 Vsense .5',
            'rc':'V1 in 0 PWL(0 0 1u 1)\nR1 in out 1000\nC1 out 0 1u',
            'rl':'V1 in 0 PWL(0 0 1u 1)\nR1 in out 100\nL1 out 0 10m',
            'mutual':'V1 in 0 PWL(0 0 1u 1)\nR1 in out 100\nL1 out 0 10m\nL2 coupled 0 20m\nR2 coupled 0 100\nK1 L1 L2 .5',
            'devices':'V1 in 0 PWL(0 0 1u 5)\nR1 in d 1000\nD1 d 0 dd\n.model dd D(IS=1e-12)\nR2 in c 1000\nR3 in b 10000\nQ1 c b 0 qq\n.model qq NPN(IS=1e-14 BF=100 CJC=2n XCJC=.2 CJE=1n RB=10 RC=1)\nR4 in e 100\nR5 pc 0 1000\nR6 pb 0 10000\nQ2 pc pb e pp\n.model pp PNP(IS=1e-14 BF=100 CJC=1n CJS=2n)'}
        with tempfile.TemporaryDirectory() as tmp:
            for name,body in fixtures.items():
                root=Path(tmp)/name
                text='Energy fixture\n'+body+'\n.options reltol=1e-7 abstol=1e-14\n.save time v(in)\n.tran 1u .003 0 1u\n.end\n'
                deck,manifest=energy.instrument(text,root/'inventory',runtime)
                solved=steady_supply.solve(deck,root/'solve',runtime,timeout_s=30)
                self.assertEqual(solved['status'],'complete')
                report=energy.assess(root/'solve/trace.raw',manifest,start_s=0,end_s=.003)
                self.assertTrue(report['accepted'],(name,report))
                if name=='ideal_transformer':
                    self.assertAlmostEqual(report['normalization_j'],abs(report['groups_j']['source_work']),delta=1e-12)
                rounded=energy.assess(root/'solve/trace.raw',manifest,start_s=0,end_s=math.nextafter(.003,math.inf))
                self.assertTrue(rounded['accepted'])
                with self.assertRaisesRegex(ValueError,'incomplete'):
                    energy.assess(root/'solve/trace.raw',manifest,start_s=0,end_s=.003001)
                if name=='rc':
                    broken=dict(manifest,parts=[p for p in manifest['parts'] if p['kind']!='c'])
                    with self.assertRaisesRegex(ValueError,'integrity'):energy.assess(root/'solve/trace.raw',broken,start_s=0,end_s=.003)

if __name__=='__main__':unittest.main()
