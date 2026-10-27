import json,shutil,tempfile,unittest
from pathlib import Path
from port_referents import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/port-referents'

class PortReferentTests(unittest.TestCase):
    def test_retained_native_counterexamples(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_order_change_or_restoration_or_continuation_rejected(self):
        for old,new in (('ORDER swapped 1 0 2 3','ORDER swapped 0 1 2 3'),('IMAGE restored1','IMAGE before1'),('CONTINUE 5 5','CONTINUE 3 5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(ROOT,out);p=out/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
