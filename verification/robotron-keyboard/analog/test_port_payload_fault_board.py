import json,lzma,tempfile,unittest
from pathlib import Path
import port_payload_fault_review as combined
from retained_evidence import check
from port_payload_combined_review import review as scope_review
ROOT=Path(__file__).resolve().parent/'reports/port-payload-fault-preflight'

class PortPayloadFaultBoardTests(unittest.TestCase):
    def test_retained_port_fault_campaign(self):
        check(ROOT)
        for root,review in ((ROOT,combined.review),(ROOT/'scope-regression',scope_review)):
            r=review(root);self.assertEqual(json.loads(json.dumps(r)),json.loads((root/'assessment.json').read_text()))
            for value in r['negativeControls'].values():
                self.assertEqual(value['scopeMetadata']['ports'],317);self.assertEqual(value['scopeMetadata']['portBits'],875)
    def run_log(self,text,mode='callback-list-user-corrupt'):
        run=json.loads((ROOT/mode/'run.json').read_text())
        ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return combined.inventory(path,ids,fault_type=mode.removesuffix('-corrupt'),contract=combined.preflight.port_contract(compiled),compiled=compiled)
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

    def test_wrong_changed_field_and_missing_refusal_reject(self):
        for mode,old,new in (('port-payload-index-corrupt','VB_PORT_PAYLOAD_FAULT field=0','VB_PORT_PAYLOAD_FAULT field=1'),('port-payload-readiness-corrupt','rejected=1 restored=1','rejected=0 restored=1')):
            text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
            self.assertIn(old,text)
            with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)

    def test_unrelated_payload_change_in_changed_stage_rejects(self):
        mode='port-payload-index-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
        a=text.index('VB_STAGE changed');b=text.index('VB_STAGE restored',a);lines=text[a:b].splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VPP_PORT '));words=lines[i].split();words[5]=str(int(words[5])^1);lines[i]=' '.join(words)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log(text[:a]+'\n'.join(lines)+'\n'+text[b:],mode)

if __name__=='__main__':unittest.main()
