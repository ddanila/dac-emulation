import json,shutil,tempfile,unittest
from pathlib import Path
from array_cache_admission import HERE,review
from array_admission import review as admission_review
from array_compact_probe import review as compact_review
from retained_evidence import check
ROOT=HERE/'reports/array-cache-admission'

class ArrayCacheAdmissionTests(unittest.TestCase):
    def test_retained_cache_and_previous_array_controls(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'admission-regression',admission_review),(ROOT/'compact-regression',compact_review)):
            actual=json.loads(json.dumps(fn(root)));expected=json.loads((root/'assessment.json').read_text())
            self.assertEqual(json.dumps(actual,sort_keys=True),json.dumps(expected,sort_keys=True))
        self.assertEqual(review(ROOT)['zeroOutputRefusals'],16)
    def test_missing_head_or_cache_refusal_rejects(self):
        for old,new in (('REFUSED 1 0\n',''),('REFUSED 1 3\n',''),('REFUSED 2 2\n',''),('IMAGE restored2','IMAGE restored1'),('CONTINUE 3 10','CONTINUE 2 10')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_unrelated_data_change_during_allocation_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE ready1');b=s.index('IMAGE_END',a);part=s[a:b];self.assertIn('VAR_WORD 0 1100',part);p.write_text(s[:a]+part.replace('VAR_WORD 0 1100','VAR_WORD 0 0100',1)+s[b:])
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
