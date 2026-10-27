import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_faults import HERE,review
from parameter_payload import review as payload_review
from retained_evidence import check
ROOT=HERE/'reports/parameter-faults'

class ParameterFaultTests(unittest.TestCase):
    def test_retained_fields_and_original_payload_controls(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'payload-regression',payload_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
        self.assertEqual(review(ROOT)['exactRestorations'],32)
    def test_missing_pointer_refusal_or_restore_reject(self):
        for old,new in (('REFUSED 1 12\n',''),('REFUSED 2 15\n',''),('IMAGE restored13_2','IMAGE restored13_1'),('CONTINUE 3 123456789abcdef01234 1.5','CONTINUE 2 123456789abcdef01234 1.5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_unrelated_metadata_change_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE changed0_1');b=s.index('IMAGE_END',a);lines=s[a:b].splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VPM_PARAM '));words=lines[i].split();words[7]=str(int(words[7])^1);lines[i]=' '.join(words);p.write_text(s[:a]+'\n'.join(lines)+'\n'+s[b:])
            with self.assertRaisesRegex(ValueError,'Wrong isolated parameter fault'):review(root)

if __name__=='__main__':unittest.main()
