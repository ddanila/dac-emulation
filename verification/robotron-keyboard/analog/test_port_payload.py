import json,shutil,tempfile,unittest
from pathlib import Path
from port_payload import HERE,review,parse
from port_referents import review as counterexample_review
from retained_evidence import check
ROOT=HERE/'reports/port-payload'

class PortPayloadTests(unittest.TestCase):
    def test_retained_payload_and_old_counterexamples(self):
        check(ROOT)
        for path,fn in ((ROOT,review),(ROOT/'old-counterexamples',counterexample_review)):
            self.assertEqual(fn(path),json.loads((path/'assessment.json').read_text()))
        self.assertEqual(review(ROOT)['resolvedNonNullPortReferences'],2)
    def test_missing_refusal_order_or_restoration_is_rejected(self):
        for old,new in (('REFUSED foreign\n',''),('ORDER swapped 1 0 2 3','ORDER swapped 0 1 2 3'),('IMAGE restored1','IMAGE before1'),('CONTINUE 5 5','CONTINUE 3 5')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';shutil.copytree(ROOT,out);p=out/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(out)
    def test_truncated_and_aliased_payload_is_rejected(self):
        text=(ROOT/'enabled.stdout').read_text();a=text.index('VPP_BEGIN ');b=text.index('IMAGE_END',a);lines=text[a:b].splitlines()
        for length in range(len(lines)):
            with self.subTest(length=length),self.assertRaises(ValueError):parse(lines[:length])
        changed=list(lines);first=next(i for i,l in enumerate(lines) if l.startswith('VPP_BIT '));changed[first+1]=changed[first]
        with self.assertRaises(ValueError):parse(changed)
        changed=list(lines);changed[-1]='VPP_END 2 9'
        with self.assertRaises(ValueError):parse(changed)

if __name__=='__main__':unittest.main()
