import json,lzma,shutil,tempfile,unittest
from pathlib import Path
import scope_signal_fault_review as combined
from scope_signal_faults import review as native_review
from retained_evidence import check
ROOT=Path(__file__).resolve().parent/'reports/scope-signal-fault-preflight'

class ScopeSignalFaultTests(unittest.TestCase):
    def test_retained_board_and_native_continuation(self):
        check(ROOT)
        r=combined.review(ROOT);self.assertEqual(json.loads(json.dumps(r)),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(r['negativeControls']),10)
        for value in r['negativeControls'].values():self.assertEqual(value['scopeMetadata']['allSignals'],651)
        self.assertEqual(native_review(ROOT/'native'),json.loads((ROOT/'native/assessment.json').read_text()))
    def run_log(self,text,mode):
        run=json.loads((ROOT/mode/'run.json').read_text());ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ngspice.log';path.write_text(text)
            return combined.inventory(path,ids,fault_type=mode.removesuffix('-corrupt'),contract=combined.preflight.port_contract(compiled),compiled=compiled)
    def test_missing_restoration_admission_or_compact_record_reject(self):
        mode='scope-signal-signed-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode()
        old_hooks=(combined.previous.records,combined.previous.bundle,combined.previous.GraphState)
        for old,new in (('admitted_unchanged=1','admitted_unchanged=0'),('restored=1','restored=0'),('VSAD_END\n','')):
            self.assertIn(old,text)
            with self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)
            self.assertEqual((combined.previous.records,combined.previous.bundle,combined.previous.GraphState),old_hooks)
    def test_wrong_changed_signal_payload_reject(self):
        mode='scope-signal-signed-corrupt';text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode();a=text.index('VB_STAGE changed');b=text.index('VB_STAGE restored',a);lines=text[a:b].splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VSA_SIGNAL '));words=lines[i].split();words[9]=str(int(words[9])^1);lines[i]=' '.join(words)
        with self.assertRaises(ValueError):self.run_log(text[:a]+'\n'.join(lines)+'\n'+text[b:],mode)
    def test_missing_native_toggle_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'native';shutil.copytree(ROOT/'native',root);p=root/'enabled.stdout';s=p.read_text();self.assertIn('TOGGLE 2 5 restored\n',s);p.write_text(s.replace('TOGGLE 2 5 restored\n',''))
            with self.assertRaises(ValueError):native_review(root)

if __name__=='__main__':unittest.main()
