import json,shutil,tempfile,unittest
from pathlib import Path
from array_cache_lifecycle import HERE,review
from retained_evidence import check
ROOT=HERE/'reports/array-cache-lifecycle'

class CacheLifecycleTests(unittest.TestCase):
    def test_retained_owner_lifecycle(self):
        check(ROOT);self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_missing_stale_refusal_or_continuation_rejects(self):
        for old,new in (('STALE 1\n',''),('REFUSED 2 1 3\n',''),('CONTINUE 1','CONTINUE 2')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_distinct_owner_or_aliased_live_cache_rejects(self):
        for field in (3,4):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';lines=p.read_text().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('OWNER 1 0'));j=next(i for i,l in enumerate(lines) if l.startswith('OWNER 1 1'));a=lines[i].split();b=lines[j].split();b[field]=hex(int(a[field],16)+16) if field==3 else a[field];lines[j]=' '.join(b);p.write_text('\n'.join(lines)+'\n')
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
