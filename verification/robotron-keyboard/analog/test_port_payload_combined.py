import json,lzma,tempfile,unittest
from pathlib import Path
import port_payload_combined_review as combined
from port_payload_typed_review import review as typed_review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/port-payload-combined-preflight'

class PortPayloadCombinedTests(unittest.TestCase):
    def test_retained_scope_and_typed_campaigns(self):
        check(ROOT)
        for root,review in ((ROOT,combined.review),(ROOT/'typed-regression',typed_review)):
            r=review(root);self.assertEqual(json.loads(json.dumps(r)),json.loads((root/'assessment.json').read_text()))
            for value in r['negativeControls'].values():
                self.assertEqual(value['scopeMetadata']['ports'],317);self.assertEqual(value['scopeMetadata']['portBits'],875)
    def run_log(self,text):
        mode='callback-list-user-corrupt';run=json.loads((ROOT/mode/'run.json').read_text())
        ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return combined.inventory(path,ids,fault_type='callback-list-user',contract=combined.preflight.port_contract(compiled),compiled=compiled)
    def test_missing_or_reordered_compact_port_records_refuse(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        originals=(combined.previous.records,combined.previous.bundle,combined.previous.GraphState)
        for old,new in (('VPPD_END\n',''),('VPPD_BEGIN 1 0 2 0','VPPD_BEGIN 1 0 3 0')):
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1))
                self.assertEqual((combined.previous.records,combined.previous.bundle,combined.previous.GraphState),originals)
    def test_port_fields_must_match_independent_compiled_declaration(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode();lines=text.splitlines()
        index=next(i for i,l in enumerate(lines) if l.startswith('VPP_PORT '));a=lines[index].split();a[5]='3' if a[5]!='3' else '1';lines[index]=' '.join(a)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log('\n'.join(lines)+'\n')

if __name__=='__main__':unittest.main()
