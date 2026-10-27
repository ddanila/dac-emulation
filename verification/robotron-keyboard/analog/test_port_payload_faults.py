import json,shutil,tempfile,unittest
from pathlib import Path
from port_payload_faults import HERE,review
from port_payload import review as payload_review
from retained_evidence import check
ROOT=HERE/'reports/port-payload-faults'

class PortFieldFaultTests(unittest.TestCase):
    def test_retained_native_fields_and_prior_vectors(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'payload-regression',payload_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
        self.assertEqual(review(ROOT)['exactRestorations'],18)
    def test_missing_refusal_restoration_and_continuation_reject(self):
        for old,new in (('REFUSED 1 8\n',''),('IMAGE restored6_2','IMAGE restored6_1'),('CONTINUE 5 5','CONTINUE 3 5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_wrong_target_field_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE changed0_1');b=s.index('IMAGE_END',a);chunk=s[a:b];rows=chunk.splitlines();i=next(i for i,x in enumerate(rows) if x.startswith('VPP_PORT '));words=rows[i].split();words[5]=str(int(words[5])^1);rows[i]=' '.join(words);p.write_text(s[:a]+'\n'.join(rows)+'\n'+s[b:])
            with self.assertRaisesRegex(ValueError,'Wrong native port field change'):review(root)

if __name__=='__main__':unittest.main()
