import json,shutil,tempfile,unittest
from pathlib import Path
from array_admission import HERE,review
from array_compact_probe import review as compact_review
from retained_evidence import check
from memory_metadata import review as memory_review
ROOT=HERE/'reports/array-admission'

class ArrayAdmissionTests(unittest.TestCase):
    def test_retained_admission_and_existing_array_controls(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'compact-regression',compact_review),(ROOT/'memory-regression',memory_review)):
            self.assertEqual(json.dumps(json.loads(json.dumps(fn(root))),sort_keys=True),json.dumps(json.loads((root/'assessment.json').read_text()),sort_keys=True))
        self.assertEqual(review(ROOT)['zeroOutputRefusals'],36)
    def test_missing_refusal_lifetime_or_continuation_rejects(self):
        for old,new in (('REFUSED 1 2\n',''),('REFUSED 2 4\n',''),('REFUSED 2 6\n',''),('LIFETIME 1\n',''),('CONTINUE 3 10','CONTINUE 2 10')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_restoration_and_wide_write_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();a=s.index('IMAGE restored2');b=s.index('IMAGE_END',a);lines=s[a:b].splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('VAR_WORD '));words=lines[i].split();words[2]='0'+words[2][1:];lines[i]=' '.join(words);p.write_text(s[:a]+'\n'.join(lines)+'\n'+s[b:])
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
