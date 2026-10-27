import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_late_class import HERE,review
from parameter_growth import review as growth
from retained_evidence import check
ROOT=HERE/'reports/parameter-late-class'

class ParameterLateClassTests(unittest.TestCase):
    def test_retained_refusals_and_supported_growth(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(growth(ROOT/'growth-regression'),json.loads((ROOT/'growth-regression/assessment.json').read_text()))
    def test_missing_late_refusal_or_continuation_reject(self):
        for mode,old,new in [('binary-enabled','REFUSED 2\n',''),('string-enabled','REFUSED 1\n',''),('real-disabled','VALUE 2 1 UNCHANGED\n',''),('binary-baseline','CONTINUE 3','CONTINUE 2')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/(mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_initial_inventory_must_precede_late_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'real-enabled.stdout';s=p.read_text();self.assertIn('VPM_BEGIN 1 1000',s);p.write_text(s.replace('VPM_BEGIN 1 1000','VPM_BEGIN 1 2000',1))
            with self.assertRaisesRegex(ValueError,'initial admitted'):review(root)

if __name__=='__main__':unittest.main()
