import json,shutil,tempfile,unittest
from pathlib import Path
from callback_ownership_contract import analyze,HERE
from callback_ownership_probe import review
from retained_evidence import check
ROOT=HERE/'reports/callback-ownership'

class CallbackOwnership(unittest.TestCase):
    def evidence(self):return json.loads((ROOT/'source-contract.json').read_text())['evidence']
    def test_native_witness_and_source_replay(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_array_association_word_must_be_owned(self):
        e=self.evidence();e['ownerLists']['excerpt']=e['ownerLists']['excerpt'].replace('unsigned long word;','unsigned long omitted;')
        with self.assertRaisesRegex(ValueError,'ownership'):analyze(e)
    def test_callback_refresh_must_precede_invocation(self):
        e=self.evidence();s=e['ownerLists']['excerpt'];s=s.replace('get_value(cur->cb_data.value);','REPLACE');s=s.replace('callback_execute(cur);','get_value(cur->cb_data.value);');s=s.replace('REPLACE','callback_execute(cur);');e['ownerLists']['excerpt']=s
        with self.assertRaisesRegex(ValueError,'execution order'):analyze(e)
    def test_part_select_history_cannot_be_omitted(self):
        e=self.evidence();e['partSelect']['excerpt']=e['partSelect']['excerpt'].replace('value_bits_','other')
        with self.assertRaisesRegex(ValueError,'partSelect'):analyze(e)
    def test_generic_cancellation_must_remain_deferred(self):
        e=self.evidence();e['removal']['excerpt']=e['removal']['excerpt'].replace('return 1;','delete obj; return 1;')
        with self.assertRaisesRegex(ValueError,'deferred'):analyze(e)
    def test_bridge_scratch_argument_requires_no_explicit_yield(self):
        e=self.evidence();e['bridgeOutput']['excerpt']=e['bridgeOutput']['excerpt'].replace('return 0;','swapcontext(a,b); return 0;')
        with self.assertRaisesRegex(ValueError,'yields'):analyze(e)
    def tamper(self,name,change):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(name+'.stdout');text=p.read_text();changed=change(text);self.assertNotEqual(text,changed);p.write_text(changed)
            with self.assertRaises(ValueError):review(root)
    def test_cancelled_callback_must_change_future_output(self):
        self.tamper('observe',lambda s:s.replace('CALLBACK 4000 A 2 0','CALLBACK 4000 B 2 0\nCALLBACK 4000 A 2 0'))
    def test_uncancelled_control_requires_all_callbacks(self):
        self.tamper('no-cancel',lambda s:s.replace('CALLBACK 4000 B 2 0\n',''))
    def test_same_head_witness_requires_equal_full_images(self):
        def change(s):
            a,b=s.split('OWN_AFTER\n');b=b.replace('VWF_BEGIN 1 3000','VWF_BEGIN 1 3001',1);return a+'OWN_AFTER\n'+b
        self.tamper('observe',change)

if __name__=='__main__':unittest.main()
