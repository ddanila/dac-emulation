import json,lzma,tempfile,unittest
from pathlib import Path
import memory_fault_review as combined
from retained_evidence import check
from memory_board_budget import native_layout
from memory_parameter_review import review as regression_review
ROOT=Path(__file__).resolve().parent/'reports/memory-fault-preflight'

class MemoryFaultTests(unittest.TestCase):
    def test_retained_memory_fault_campaign(self):
        check(ROOT)
        r=combined.review(ROOT);self.assertEqual(json.loads(json.dumps(r)),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(r['negativeControls']),9)
        regression=ROOT/'parameter-regression';self.assertEqual(json.loads(json.dumps(regression_review(regression))),json.loads((regression/'assessment.json').read_text()))
        for value in r['negativeControls'].values():
            self.assertEqual(value['scopeMetadata']['memories'],3)
            self.assertEqual(value['scopeMetadata']['memoryReadPorts'],23)
            self.assertEqual(value['scopeMetadata']['parameters'],56)
            self.assertEqual(value['scopeMetadata']['allSignals'],651)

    def run_log(self,text,mode='callback-list-user-corrupt'):
        run=json.loads((ROOT/mode/'run.json').read_text())
        ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return combined.inventory(path,ids,fault_type=mode.removesuffix('-corrupt'),contract=combined.preflight.port_contract(compiled),compiled=compiled,memory_offset=native_layout(ROOT))
    def test_missing_or_reordered_compact_port_records_refuse(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        originals=(combined.previous.records,combined.previous.bundle,combined.previous.GraphState)
        for old,new in (('VMMD_END\n',''),('VMMD_BEGIN 1 0 2 0','VMMD_BEGIN 1 0 3 0')):
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1))
                self.assertEqual((combined.previous.records,combined.previous.bundle,combined.previous.GraphState),originals)
    def test_parameter_flags_must_match_independent_compiled_declaration(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode();lines=text.splitlines()
        index=next(i for i,l in enumerate(lines) if l.startswith('VPM_BINARY '));a=lines[index].split();a[2]=str(int(a[2])^1);lines[index]=' '.join(a)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log('\n'.join(lines)+'\n')

    def test_wrong_changed_field_and_missing_refusal_reject(self):
        for mode,old,new in (('memory-name-corrupt','VB_MEMORY_FAULT field=0','VB_MEMORY_FAULT field=1'),('memory-storage-pointer-corrupt','rejected=1 restored=1','rejected=0 restored=1')):
            text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
            self.assertIn(old,text)
            with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)

    def test_unrelated_payload_change_in_changed_stage_rejects(self):
        mode='memory-name-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
        a=text.index('VB_STAGE changed');b=text.index('VB_STAGE restored',a);lines=text[a:b].splitlines()
        i=[i for i,l in enumerate(lines) if l.startswith('VMM_NAME ')][1];words=lines[i].split();raw=bytearray.fromhex(words[1]);raw[0]^=1;words[1]=raw.hex();lines[i]=' '.join(words)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log(text[:a]+'\n'.join(lines)+'\n'+text[b:],mode)

    def test_memory_names_match_compiled_declarations(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        self.assertIn('VMM_NAME 726f6d00',text)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log(text.replace('VMM_NAME 726f6d00','VMM_NAME 736f6d00',1))

if __name__=='__main__':unittest.main()
