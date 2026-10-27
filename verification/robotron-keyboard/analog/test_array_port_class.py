import json,shutil,tempfile,unittest
from pathlib import Path
from array_port_class import HERE,review
from memory_fault_continue import review as memory_review
from retained_evidence import check
from array_family_probe import review as family_review
ROOT=HERE/'reports/array-port-class'

class ArrayPortClassTests(unittest.TestCase):
    def test_retained_native_controls(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'memory-regression',memory_review),(ROOT/'family-regression',family_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_refusal_or_changed_continuation_reject(self):
        for old,new in [('REFUSED 2\n',''),('CONTINUE 7 5 7','CONTINUE 7 5 5'),('IMAGE restored2','IMAGE restored1')]:
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_replacement_must_preserve_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE base1');b=s.index('IMAGE_END',a);part=s[a:b];self.assertIn('VAR_WORD 0 1100',part);p.write_text(s[:a]+part.replace('VAR_WORD 0 1100','VAR_WORD 0 0100',1)+s[b:])
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
