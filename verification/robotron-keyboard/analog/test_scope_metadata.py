import json
from pathlib import Path
import shutil
import tempfile
import unittest
from scope_metadata import HERE, review
from retained_evidence import check
from scope_admission import review as admission_review
from scope_probe import review as membership_review
from signal_scope_scan import review as signal_review

class ScopeMetadataTests(unittest.TestCase):
    def test_retained_native_controls(self):
        root=HERE/'reports/scope-metadata';check(root)
        for folder,reviewer in ((root,review),(root/'admission-controls',admission_review),(root/'membership-controls',membership_review),(root/'signal-controls',signal_review)):
            self.assertEqual(json.loads(json.dumps(reviewer(folder))),json.loads((folder/'assessment.json').read_text()))
    def test_missing_fault_restoration_function_or_continuation_is_rejected(self):
        for old,new in (('REFUSED intern\n',''),('IMAGE restored1','IMAGE before1'),('CONTINUE 5 2','CONTINUE 3 2'),('VSM_FUNCTION ','OMITTED_FUNCTION '),('VSM_TIME 2 0 0','VSM_TIME 0 0 0')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(HERE/'reports/scope-metadata',out)
                p=out/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new))
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
