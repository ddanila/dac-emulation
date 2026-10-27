import json,shutil,tempfile,unittest
from pathlib import Path
from parameter_payload import HERE,review,parse
from scope_payload_gaps import review as gap_review
from retained_evidence import check
ROOT=HERE/'reports/parameter-payload'

class ParameterPayloadTests(unittest.TestCase):
    def test_retained_native_families_and_original_gap(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'old-gaps',gap_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_refusal_restore_and_continuation_reject(self):
        for old,new in (('REFUSED width\n',''),('IMAGE restored2','IMAGE before2'),('CONTINUE 3 123456789abcdef01234 1.5','CONTINUE 2 123456789abcdef01234 1.5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_truncated_aliased_and_malformed_storage_reject(self):
        text=(ROOT/'enabled.stdout').read_text();a=text.index('VPM_BEGIN ');b=text.index('IMAGE_END',a);lines=text[a:b].splitlines()
        for i in range(len(lines)):
            with self.subTest(i=i),self.assertRaises(ValueError):parse(lines[:i])
        rows=[i for i,l in enumerate(lines) if l.startswith('VPM_PARAM ')];bad=list(lines);first=bad[rows[0]].split();other=bad[rows[1]].split();other[1]=first[1];bad[rows[1]]=' '.join(other)
        with self.assertRaises(ValueError):parse(bad)
        bad=list(lines);i=next(i for i,l in enumerate(bad) if l.startswith('VPM_WORD '));a=bad[i].split();a[2]='1'+'0'*32;bad[i]=' '.join(a)
        with self.assertRaises(ValueError):parse(bad)

if __name__=='__main__':unittest.main()
