import json,lzma,tempfile,unittest
from pathlib import Path
import scope_metadata_combined_review as combined
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/scope-metadata-combined-preflight'

class ScopeMetadataCombinedTests(unittest.TestCase):
    def test_retained_all_startup_faults(self):
        check(ROOT)
        self.assertEqual(json.loads(json.dumps(combined.review(ROOT))),json.loads((ROOT/'assessment.json').read_text()))
    def run_log(self,text):
        mode='callback-list-user-corrupt';run=json.loads((ROOT/mode/'run.json').read_text())
        ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return combined.inventory(path,ids,fault_type='callback-list-user',contract=combined.preflight.port_contract(compiled),compiled=compiled)
    def test_missing_sequence_and_metadata_refuse_without_leaking_adapters(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        original_records,original_bundle=combined.previous.records,combined.previous.bundle
        mutations=[lambda s:s.replace('VSMD_BEGIN 1 0 2 0','VSMD_BEGIN 1 0 3 0',1),
            lambda s:s.replace('VSMD_END\n','',1),
            lambda s:s.replace('VSM_TIME 0 0 0','VSM_TIME 999 0 0',1)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed=mutate(text);self.assertNotEqual(changed,text)
                with self.assertRaises(ValueError):self.run_log(changed)
                self.assertIs(combined.previous.records,original_records);self.assertIs(combined.previous.bundle,original_bundle)
    def test_canonical_metadata_restoration_is_required(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        # Time differs only in the compact restored record. The dense old layer
        # still restores; the combined metadata time binding must reject it.
        changed=text.replace('VSMD_BEGIN 1 0 2 0','VSMD_BEGIN 1 1 2 0',1)
        self.assertNotEqual(changed,text)
        with self.assertRaises(ValueError):self.run_log(changed)

if __name__=='__main__':unittest.main()
