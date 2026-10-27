import json
from pathlib import Path
import shutil
import tempfile
import unittest
from scope_admission import HERE,review
from retained_evidence import check
from scope_probe import review as membership_review
from signal_scope_scan import review as signal_review

class ScopeAdmissionTests(unittest.TestCase):
    def test_retained_new_and_existing_native_controls(self):
        root=HERE/'reports/scope-admission';check(root)
        for folder,reviewer in ((root,review),(root/'membership-controls',membership_review),(root/'signal-controls',signal_review)):
            self.assertEqual(json.loads(json.dumps(reviewer(folder))),json.loads((folder/'assessment.json').read_text()))
    def test_missing_refusal_or_changed_restoration_is_rejected(self):
        for old,new in (('REFUSED intern\n',''),('IMAGE restored1','IMAGE before1'),('CONTINUE 5 2','CONTINUE 3 2')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(HERE/'reports/scope-admission',out)
                p=out/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
