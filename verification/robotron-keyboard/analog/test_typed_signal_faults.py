import copy,json,shutil,tempfile,unittest
from pathlib import Path
from typed_signal_fault_preflight import HERE,review
from typed_signal_fault_native import review as native_review
from typed_signal_fault_review import typed_changed
from retained_evidence import check
ROOT=HERE/'reports/typed-signal-fault-preflight'
NATIVE=HERE/'reports/typed-signal-fault-native'


class TypedSignalFaults(unittest.TestCase):
    def test_complete_combined_native_fault_replay(self):
        check(ROOT);self.assertEqual(json.loads(json.dumps(review(ROOT))),json.loads((ROOT/'assessment.json').read_text()))
    def test_original_native_continuation_and_paired_guards(self):
        check(NATIVE);self.assertEqual(native_review(NATIVE),json.loads((NATIVE/'assessment.json').read_text()))
    def native_tamper(self,old,new,mode='enabled'):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(NATIVE,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):native_review(root)
    def test_active_mutation_refusal_required(self):self.native_tamper('TYPED_ACTIVE_REFUSED\n','')
    def test_wrong_restore_field_guard_required(self):self.native_tamper('TYPED_GUARD 4\n','')
    def test_original_continuation_is_independent(self):self.native_tamper('CALLBACK a 7','CALLBACK a 5','baseline')
    def test_all_native_faults_must_restore(self):self.native_tamper('STATE typed-restored-5','STATE other')
    def test_foreign_cache_pointer_must_refuse(self):self.native_tamper('REFUSED typed-4\n','')
    def test_only_selected_metadata_field_may_change(self):
        before=dict(portState={'counts':[1,1,0]},typedSignals={'rows':[dict(id=3,signed=0,msb=23)]},other={'value':5})
        bindings=[dict(id=2),dict(id=3)];after=copy.deepcopy(before);after['typedSignals']['rows'][0]['signed']=1
        typed_changed(before,after,0,bindings);after['other']['value']=6
        with self.assertRaisesRegex(ValueError,'unrelated'):typed_changed(before,after,0,bindings)
    def test_native_range_fault_uses_exact_bit_change(self):
        before=dict(portState={'counts':[0,1,0]},typedSignals={'rows':[dict(id=3,signed=0,msb=23)]});after=copy.deepcopy(before);after['typedSignals']['rows'][0]['msb']=24
        with self.assertRaisesRegex(ValueError,'wrong metadata'):typed_changed(before,after,1,[dict(id=3)])


if __name__=='__main__':unittest.main()
