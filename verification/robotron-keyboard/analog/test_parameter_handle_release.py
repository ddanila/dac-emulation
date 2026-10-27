import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_handle_release import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/parameter-handle-release'

class ParameterHandleReleaseTests(unittest.TestCase):
    def test_retained_release_controls(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_release_or_changed_continuation_reject(self):
        for mode,old,new in [('enabled','RELEASE 2 test.S 1 1 SAME\n',''),('disabled','RELEASE 1 test.P 0 1 SAME','RELEASE 1 test.P 0 0 SAME'),('baseline','CONTINUE 3 123456789abcdef01234 1.5','CONTINUE 3 123456789abcdef01234 2.5')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/('none-'+mode+'.stdout');s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_changed_inventory_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'none-enabled.stdout';s=p.read_text();old='VPM_BYTES 41004200';self.assertIn(old,s);p.write_text(s.replace(old,'VPM_BYTES 41004300',1))
            with self.assertRaisesRegex(ValueError,'Release changed'):review(root)

if __name__=='__main__':unittest.main()
