import json,lzma,tempfile,unittest
from pathlib import Path
import scope_metadata_fault_review as fault
from scope_metadata_combined_review import review as regression_review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/scope-metadata-fault-preflight'

class ScopeMetadataFaultTests(unittest.TestCase):
    def test_retained_scope_faults_and_prior_regressions(self):
        check(ROOT)
        for root,review in ((ROOT,fault.review),(ROOT/'regression',regression_review)):
            self.assertEqual(json.loads(json.dumps(review(root))),json.loads((root/'assessment.json').read_text()))
    def run_log(self,text):
        mode='scope-metadata-function-width-corrupt';run=json.loads((ROOT/mode/'run.json').read_text())
        ids=fault.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return fault.inventory(path,ids,fault_type=mode.removesuffix('-corrupt'),contract=fault.preflight.port_contract(compiled),compiled=compiled)
    def test_wrong_function_field_rejected(self):
        text=lzma.decompress((ROOT/'scope-metadata-function-width-corrupt/ngspice.log.xz').read_bytes()).decode()
        start=text.index('VB_STAGE changed');before=text[:start];changed=text[start:].replace('VSM_FUNCTION 5 2 3','VSM_FUNCTION 4 2 3',1)
        self.assertNotEqual(changed,text[start:])
        with self.assertRaisesRegex(ValueError,'wrong metadata'):self.run_log(before+changed)
    def test_missing_restoration_or_false_direct_detection_rejected(self):
        text=lzma.decompress((ROOT/'scope-metadata-function-width-corrupt/ngspice.log.xz').read_bytes()).decode()
        for old,new in (('field=3 direct=1','field=3 direct=0'),('rejected=0 restored=1','rejected=0 restored=0')):
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1))

if __name__=='__main__':unittest.main()
