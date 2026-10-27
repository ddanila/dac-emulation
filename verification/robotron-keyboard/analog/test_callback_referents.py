import json,shutil,tempfile,unittest
from pathlib import Path
from callback_referents import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/callback-referents'


class CallbackReferents(unittest.TestCase):
    def test_native_witness_replays(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))

    def tamper(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)

    def test_node_change_requires_behavioral_difference(self):self.tamper('enabled','NODE 3','NODE -6')
    def test_original_continuation_is_independent(self):self.tamper('baseline','CALLBACK 5','CALLBACK 10')
    def test_faults_must_restore(self):self.tamper('enabled','RESTORED -6','RESTORED 10')
    def test_identical_list_witness_is_required(self):
        self.tamper('enabled','VCL_BEGIN 1 1000','VCL_BEGIN 1 1001')
    def test_cache_observation_is_required(self):self.tamper('enabled','IMAGE bit-cache','IMAGE other')


if __name__=='__main__':unittest.main()
