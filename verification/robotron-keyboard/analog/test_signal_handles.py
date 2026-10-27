import json,shutil,tempfile,unittest
from pathlib import Path
from signal_handles import HERE,review,parse
from retained_evidence import check
ROOT=HERE/'reports/signal-handles'


class SignalHandles(unittest.TestCase):
    def test_retained_native_metadata_and_refusals(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def test_prior_callback_observation_on_new_runtime(self):
        from callback_referents import review as replay
        r=ROOT/'callback-regression';self.assertEqual(replay(r),json.loads((r/'assessment.json').read_text()))

    def test_prior_native_owner_lifecycle_on_new_runtime(self):
        from callback_owner_lifecycle import review as replay
        r=ROOT/'owner-regression';self.assertEqual(replay(r),json.loads((r/'assessment.json').read_text()))

    def tamper(self,old,new,mode='enabled'):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)

    def test_scope_pointer_refusal_required(self):self.tamper('REFUSED scope\n','')
    def test_cache_pointer_refusal_required(self):self.tamper('REFUSED cache\n','')
    def test_native_original_continuation_required(self):self.tamper('CALLBACK 5','CALLBACK 10','baseline')
    def test_restoration_required(self):self.tamper('IMAGE cached-restored','IMAGE missing')
    def test_index_value_must_be_observed(self):
        s=(ROOT/'enabled.stdout').read_text();s=s[s.index('IMAGE index-value'):];line=next(line for line in s.splitlines() if line.startswith('VSH_BIT 0 '))
        self.assertTrue(line.endswith(' 7'));self.tamper(line,line[:-1]+'0')
    def test_node_binding_must_be_observed(self):
        s=(ROOT/'enabled.stdout').read_text();start=s.index('IMAGE node');line=next(line for line in s[start:].splitlines() if line.startswith('VSH_SIGNAL '));a=line.split();a[5]='999999';self.tamper(line,' '.join(a))
    def test_signal_class_is_not_inferred_from_name(self):self.tamper('10signal_reg','7unknown')
    def test_no_partial_image_accepted(self):self.tamper('VSH_END 2','VSH_END 3')


if __name__=='__main__':unittest.main()
