import json
import unittest
from postreset_state_review import HERE, SOURCE_NAMES, validate_receipt
from postreset_state_capture import VARIANTS
from ttl7406_probe import sha


class StateReceiptTests(unittest.TestCase):
    def receipt(self,mode='check'):
        code=2 if mode in ('immediate','delayed') else 0
        return {'completed':True,'mode':mode,'exitCode':code,'expectedExitCode':code,
                'inputs':{'io.cir':'deck'},'sourceRunSha256':'source','externalDependencies':['dep'],
                'runtime':'runtime','candidateBuildSha256':'build','environment':dict(VARIANTS[mode]),
                'sources':{n:sha(HERE/n) for n in SOURCE_NAMES},'storage':{'waveform.raw':{}},
                'limits':{'logicalLogBytes':100,'compressedLogBytes':100,'freeSpaceReserveBytes':10,'timeoutSeconds':10},
                'log':{'exitCode':code,'logicalLimitBytes':100,'compressedLimitBytes':100,'bytes':80,'compressedBytes':60}}

    def check(self,r,mode='check'):
        validate_receipt(r,{'environment':{},'externalDependencies':['dep']},{'io.cir':'deck'},mode,'runtime','build','source')

    def test_retained_immediate_capture_matches_contract(self):
        folder=HERE/'reports/postreset-state-immediate'
        source=HERE/'reports/postreset-newton-retry/off/run.json'
        r=json.loads((folder/'run.json').read_text());prior=json.loads(source.read_text())
        inputs=dict(prior['inputs'],**{'io.cir':prior['deckSha256']})
        validate_receipt(r,prior,inputs,'immediate',r['runtime'],sha(folder/'build.json'),sha(source))

    def test_positive_and_intentional_negative_have_distinct_exit_contracts(self):
        for mode in VARIANTS: self.check(self.receipt(mode),mode)
        bad=self.receipt('delayed');bad['exitCode']=0
        with self.assertRaisesRegex(ValueError,'termination'):self.check(bad,'delayed')

    def test_incomplete_changed_conditions_and_exceeded_budgets_rejected(self):
        mutations=[('completed',False),('error','interrupted'),('runtime','other'),('inputs',{}),('environment',{}),
                   ('sourceRunSha256','other'),('sources',{}),('storage',{})]
        for key,value in mutations:
            r=self.receipt();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.check(r)
        for field,value in [('bytes',101),('compressedBytes',101),('logicalLimitBytes',101),('exitCode',2)]:
            r=self.receipt();r['log'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check(r)
        for field,value in [('logicalLogBytes',True),('freeSpaceReserveBytes',0),('timeoutSeconds',float('nan'))]:
            r=self.receipt();r['limits'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check(r)


if __name__=='__main__':unittest.main()
