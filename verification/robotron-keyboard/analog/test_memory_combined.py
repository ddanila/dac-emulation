import json,lzma,tempfile,unittest
from pathlib import Path
import memory_parameter_review as combined
from retained_evidence import check
from memory_board_budget import native_layout
from memory_log_replay import review as logger_review
from memory_compact import MemoryDecoder
from memory_port_review import review as regression_review
ROOT=Path(__file__).resolve().parent/'reports/memory-combined-preflight'

class MemoryCombinedTests(unittest.TestCase):
    def test_retained_port_fault_campaign(self):
        check(ROOT)
        r=combined.review(ROOT);self.assertEqual(json.loads(json.dumps(r)),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(r['negativeControls']),14)
        regression=ROOT/'port-regression';self.assertEqual(json.loads(json.dumps(regression_review(regression))),json.loads((regression/'assessment.json').read_text()))
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
        for mode,old,new in (('parameter-word-corrupt','VB_PARAMETER_FAULT field=0','VB_PARAMETER_FAULT field=1'),('parameter-width-corrupt','rejected=1 restored=1','rejected=0 restored=1')):
            text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
            self.assertIn(old,text)
            with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)

    def test_unrelated_payload_change_in_changed_stage_rejects(self):
        mode='parameter-word-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
        a=text.index('VB_STAGE changed');b=text.index('VB_STAGE restored',a);lines=text[a:b].splitlines()
        i=[i for i,l in enumerate(lines) if l.startswith('VPM_PARAM ')][1];words=lines[i].split();words[5]=str(int(words[5])^1);lines[i]=' '.join(words)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log(text[:a]+'\n'.join(lines)+'\n'+text[b:],mode)

    def test_extra_raw_storage_bit_rejects_even_outside_declared_width(self):
        mode='parameter-word-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
        a=text.index('VB_STAGE changed');b=text.index('VB_STAGE restored',a);lines=text[a:b].splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VPM_WORD '));words=lines[i].split();words[2]=format(int(words[2],16)^(1<<40),'016x');lines[i]=' '.join(words)
        with self.assertRaisesRegex(ValueError,'wrong field or unrelated state'):self.run_log(text[:a]+'\n'.join(lines)+'\n'+text[b:],mode)

    def test_memory_names_match_compiled_declarations(self):
        text=lzma.decompress((ROOT/'callback-list-user-corrupt/ngspice.log.xz').read_bytes()).decode()
        self.assertIn('VMM_NAME 726f6d00',text)
        with self.assertRaisesRegex(ValueError,'compiled declaration'):self.run_log(text.replace('VMM_NAME 726f6d00','VMM_NAME 736f6d00',1))

    def test_native_memory_logger_reconstruction_and_failed_decode(self):
        root=ROOT/'logger-replay';self.assertEqual(logger_review(root),json.loads((root/'assessment.json').read_text()))
        lines=(root/'compact.txt').read_text().splitlines();first=lines[:lines.index('VMMD_END')+1];decoder=MemoryDecoder()
        bad=list(first);a=bad[0].split();a[3]='2';bad[0]=' '.join(a)
        with self.assertRaises(ValueError):decoder.decode(bad)
        self.assertEqual(decoder.sequence,0);self.assertIsNone(decoder.body)
        self.assertTrue(decoder.decode(first).startswith('VMM_BEGIN '))

if __name__=='__main__':unittest.main()
