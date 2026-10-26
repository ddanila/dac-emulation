import copy
import json
from pathlib import Path
import unittest
from postreset_refinement_review import voltage_gate, validate_refinement
from postreset_refinement_capture import SOURCES
from ttl7406_probe import sha


def comparison(**values):
    return {'signals':{n:{'unit':'V','maximumAbsoluteDifference':v} for n,v in values.items()}}


class GateTests(unittest.TestCase):
    def test_refinement_requires_matching_completed_experiment(self):
        here=Path(__file__).resolve().parent
        control=json.loads((here/'reports/postreset-startup-fixes/combined/run.json').read_text())
        receipt={k:control[k] for k in ('runtime','environment','externalDependencies','candidateBuildSha256')}
        receipt.update(completed=True,exitCode=0,stepNs=12.5,endSeconds=.00116,
                       originalInputs=control['inputs'],inputs=control['inputs'],
                       coarseRunSha256='coarse',sourceRunSha256='source',
                       sources={n:sha(here/n) for n in SOURCES},storage={'waveform.raw':{}},
                       log={'exitCode':0,'bytes':10,'compressedBytes':5},
                       limits={'logicalLogBytes':20,'compressedLogBytes':10})
        def check(r):validate_refinement(r,control,'coarse','source',12.5)
        check(receipt)
        for key,value in [('completed',False),('error','timeout'),('exitCode',2),
                          ('stepNs',25),('endSeconds',.00002),('runtime',{}),
                          ('environment',{}),('externalDependencies',[]),
                          ('candidateBuildSha256','other'),('originalInputs',{}),
                          ('inputs',{}),('storage',{}),('sources',{}),
                          ('coarseRunSha256','other'),('sourceRunSha256','other')]:
            with self.subTest(key=key):
                bad=copy.deepcopy(receipt);bad[key]=value
                with self.assertRaises(ValueError):check(bad)
        for field in ('bytes','compressedBytes'):
            bad=copy.deepcopy(receipt);bad['log'][field]=100
            with self.assertRaises(ValueError):check(bad)

    def test_every_voltage_must_pass_both_requirements(self):
        prior=comparison(a=.02,b=.004)
        self.assertTrue(voltage_gate(prior,comparison(a=.01,b=.003))['passed'])
        for fine,node,reason in ((comparison(a=.010001,b=.003),'a','Exceeds 10 mV'),
                                 (comparison(a=.009,b=.005),'b','Difference grows under refinement')):
            result=voltage_gate(prior,fine)
            self.assertFalse(result['passed'])
            self.assertIn(reason,result['failures'][node]['reasons'])

    def test_missing_invalid_or_changed_observations_are_not_success(self):
        prior=comparison(a=.02,b=.004)
        for bad in (comparison(a=.001),comparison(a=float('nan'),b=.001),
                    comparison(a=-1,b=.001),comparison(a=float('inf'),b=.001)):
            with self.assertRaises(ValueError):voltage_gate(prior,bad)
        bad=copy.deepcopy(prior);bad['signals']['a']['unit']='A'
        with self.assertRaises(ValueError):voltage_gate(prior,bad)
        with self.assertRaises(ValueError):voltage_gate(comparison(),comparison())


if __name__=='__main__':unittest.main()
