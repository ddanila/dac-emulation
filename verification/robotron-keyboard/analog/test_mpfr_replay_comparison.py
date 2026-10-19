import copy
import unittest
from compare_mpfr_replays import compatible,step_and_normalized


class ReplayComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a={'report':{'sourceReportSha256':'source','ngspiceRuntime':{'identity':'runtime'},
            'patchSha256':'patch','stopSeconds':1,'integration':{'selection':'gear'},'mode':'256',
            'artifacts':{'build-provenance.json':'build'}},'stepNs':50,'normalizedDeck':'same'}

    def test_only_declared_precision_or_timestep_difference(self):
        b=copy.deepcopy(self.a);b['report']['mode']='512'
        compatible(self.a,b,'precision')
        with self.assertRaises(ValueError):compatible(self.a,b,'timestep')
        b['report']['mode']='256';b['stepNs']=25
        compatible(self.a,b,'timestep')
        with self.assertRaises(ValueError):compatible(self.a,b,'precision')

    def test_changed_physics_inputs_or_runtime_rejected(self):
        for field in ('sourceReportSha256','ngspiceRuntime','patchSha256','stopSeconds','integration'):
            b=copy.deepcopy(self.a);b['stepNs']=25;b['report'][field]='different'
            with self.subTest(field=field),self.assertRaises(ValueError):compatible(self.a,b,'timestep')
        b=copy.deepcopy(self.a);b['stepNs']=25;b['normalizedDeck']='different resistor'
        with self.assertRaises(ValueError):compatible(self.a,b,'timestep')
        b=copy.deepcopy(self.a);b['stepNs']=25;b['report']['artifacts']['build-provenance.json']='different'
        with self.assertRaises(ValueError):compatible(self.a,b,'timestep')

    def test_normalization_preserves_endpoint_and_stimulus(self):
        source='V1 a 0 PWL(0 0 1n 5)\n.tran 50.0n .001\n.end\n'
        step,normalized=step_and_normalized(source)
        self.assertEqual(step,50)
        self.assertEqual(normalized,source.replace('50.0n','STEPn'))
        self.assertNotEqual(normalized,step_and_normalized(source.replace('.001','.002'))[1])
        with self.assertRaises(ValueError):step_and_normalized(source+'.tran 25n .001\n')


if __name__=='__main__':unittest.main()
