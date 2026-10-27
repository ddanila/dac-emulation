import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_growth import HERE,review
from parameter_class import review as classes
from retained_evidence import check
ROOT=HERE/'reports/parameter-growth'

class ParameterGrowthTests(unittest.TestCase):
    def test_retained_growth_and_class_regression(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(classes(ROOT/'class-regression'),json.loads((ROOT/'class-regression/assessment.json').read_text()))
    def test_missing_allocation_refusal_or_original_continuation_reject(self):
        for mode,old,new in [('enabled','ADDED 2 2\n',''),('disabled','REFUSED 2\n',''),('baseline','CONTINUE 3','CONTINUE 2')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_growth_cannot_change_existing_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();prefix,tail=s.split('IMAGE after1_0\n',1);old='VPM_BYTES 41004200';self.assertIn(old,tail);p.write_text(prefix+'IMAGE after1_0\n'+tail.replace(old,'VPM_BYTES 41004300',1))
            with self.assertRaisesRegex(ValueError,'Growth changed existing'):review(root)

if __name__=='__main__':unittest.main()
