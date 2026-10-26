import copy
import json
from pathlib import Path
import unittest
from postreset_adc_review import validate_capture, HERE, SOURCES
from ttl7406_probe import sha


class ADCReviewTests(unittest.TestCase):
    def setUp(self):
        self.control = json.loads((HERE/'reports/postreset-startup-fixes/combined/run.json').read_text())
        c = self.control
        self.receipt = {key:copy.deepcopy(c[key]) for key in
                        ('runtime','externalDependencies','candidateBuildSha256','sourceRunSha256','inputs','storage')}
        self.receipt.update(completed=True,exitCode=0,stepNs=25,endSeconds=.00116,adcCrossings='on',
                            environment=dict(c['environment'],ROBOTRON_ADC_CROSSINGS='1'),
                            coarseRunSha256='baseline',originalInputs=c['inputs'],
                            sources={name:sha(HERE/name) for name in SOURCES},
                            log={'exitCode':0,'bytes':100,'compressedBytes':50},
                            limits={'logicalLogBytes':100,'compressedLogBytes':50})

    def test_accepts_only_the_matching_capture_contract(self):
        validate_capture(self.receipt,self.control,'baseline',25)
        changes = {'completed':False,'exitCode':2,'error':'failed','stepNs':12.5,
                   'endSeconds':20e-6,'adcCrossings':'off','coarseRunSha256':'other',
                   'sourceRunSha256':'other','candidateBuildSha256':'other',
                   'environment':self.control['environment'],'sources':{},'storage':{},
                   'inputs':{},'originalInputs':{},'runtime':{},'externalDependencies':[]}
        for key,value in changes.items():
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_capture(dict(self.receipt,**{key:value}),self.control,'baseline',25)

    def test_failed_or_over_budget_transport_cannot_be_accepted(self):
        for key,value in (('exitCode',2),('bytes',101),('bytes',0),('compressedBytes',51)):
            bad = copy.deepcopy(self.receipt);bad['log'][key] = value
            with self.assertRaises(ValueError):validate_capture(bad,self.control,'baseline',25)


if __name__ == '__main__': unittest.main()
