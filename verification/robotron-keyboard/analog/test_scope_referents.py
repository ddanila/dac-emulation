import json
from pathlib import Path
import shutil
import tempfile
import unittest
from scope_referents import HERE,review
from retained_evidence import check

class ScopeReferentTests(unittest.TestCase):
    def test_retained_native_controls(self):
        root=HERE/'reports/scope-referents';check(root)
        self.assertEqual(review(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_or_changed_witness_and_continuation_refuse(self):
        for old,new in (('IMAGE units','IMAGE before'),('UNITS 0.001','UNITS 1.000'),('CONTINUE 5 2.000','CONTINUE 3 2.000'),('VSC_BEGIN 1 1000','VSC_BEGIN 1 1001')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'report';shutil.copytree(HERE/'reports/scope-referents',root)
                p=root/'enabled.stdout';text=p.read_text();self.assertIn(old,text);p.write_text(text.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
