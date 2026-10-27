import json,shutil,tempfile,unittest
from pathlib import Path
from memory_fault_continue import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/memory-fault-continue'

class MemoryContinuationTests(unittest.TestCase):
    def test_retained_native_controls(self):
        check(ROOT)
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_fault_and_changed_continuation_reject(self):
        for mode,old,new in [('enabled','FAULT 2 4 restored\n',''),('enabled','CONTINUE 7 5 7','CONTINUE 7 5 5'),('baseline','INDEXED 5','INDEXED 4'),('disabled','CONTINUE 7 5 7','CONTINUE 3 10 3')]:
            with self.subTest(mode=mode,old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_mutated_payload_and_missing_cache_reject(self):
        for stage,old,new in [('changed1','6c656d6f727900','6c656d6f727800'),('values2','VAR_WORD 0 0011','VAR_WORD 0 1011'),('arrays2','VAR_CACHE_WORD 1','VAR_CACHE_WORD 0')]:
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE '+stage);b=s.index('IMAGE_END',a);part=s[a:b];self.assertIn(old,part);p.write_text(s[:a]+part.replace(old,new,1)+s[b:])
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
