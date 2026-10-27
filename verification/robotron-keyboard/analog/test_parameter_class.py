import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_class import HERE,review
from parameter_faults import review as faults_review
from retained_evidence import check
ROOT=HERE/'reports/parameter-class'

class ParameterClassTests(unittest.TestCase):
    def test_retained_classes_and_existing_faults(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'fault-regression',faults_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_subclass_refusal_or_changed_continuation_reject(self):
        for mode,old,new in [('binary-enabled','REFUSED 2 binary\n',''),('string-disabled','CLASS string 1','CLASS string 0'),('real-enabled','CONTINUE 3 123456789abcdef01234 1.5','CONTINUE 3 123456789abcdef01234 2.5'),('none-baseline','VALUES 3','VALUES 2')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_supported_inventory_must_remain_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'none-enabled.stdout';s=p.read_text();self.assertIn('VPM_END 4',s);p.write_text(s.replace('VPM_END 4','VPM_END 3',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
