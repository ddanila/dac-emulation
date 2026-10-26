import copy
from pathlib import Path
import unittest
from startup_fixes_capture import VARIANTS
from startup_fixes_review import validate_receipt
from ttl7406_probe import sha

class InteractionControlsTests(unittest.TestCase):
    def test_rejects_mixed_candidate_runtime_inputs_and_flags(self):
        baseline={'inputs':{'io.cir':'deck'},'environment':{'ROBOTRON_BARRIER':'on'}}
        for mode in VARIANTS:
            receipt={'exitCode':0,'inputs':baseline['inputs'],
                     'candidateBuildSha256':'build','runtime':'runtime',
                     'environment':dict(baseline['environment'],**VARIANTS[mode]),
                     'variantControllerSha256':sha(Path(__file__).with_name('startup_fixes_capture.py'))}
            validate_receipt(receipt,baseline,mode,'build','runtime')
            for key,value in [('exitCode',1),('inputs',{}),('candidateBuildSha256','other'),
                              ('runtime','other'),('environment',{}),('variantControllerSha256','other')]:
                with self.subTest(mode=mode,key=key):
                    changed=copy.deepcopy(receipt);changed[key]=value
                    with self.assertRaises(ValueError):validate_receipt(changed,baseline,mode,'build','runtime')

if __name__=='__main__':unittest.main()
