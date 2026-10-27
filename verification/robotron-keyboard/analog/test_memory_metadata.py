import json,shutil,tempfile,unittest
from pathlib import Path
from memory_metadata import HERE,parse,review
from parameter_faults import review as parameter_review
from retained_evidence import check
ROOT=HERE/'reports/memory-metadata'

class MemoryMetadataTests(unittest.TestCase):
    def test_retained_native_and_parameter_controls(self):
        check(ROOT)
        for root,fn in ((ROOT,review),(ROOT/'parameter-regression',parameter_review)):
            self.assertEqual(fn(root),json.loads((root/'assessment.json').read_text()))
    def test_missing_refusal_and_wrong_restoration_reject(self):
        for old,new in (('REFUSED 1 1\n',''),('REFUSED 2 4\n',''),('IMAGE restored2','IMAGE restored1'),('CONTINUE 3 10','CONTINUE 2 10')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'evidence';shutil.copytree(ROOT,root);p=root/'enabled.stdout';s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
                with self.assertRaises(ValueError):review(root)
    def test_malformed_name_and_duplicate_identity_reject(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();a=lines.index('IMAGE before1')+1;b=lines.index('IMAGE_END',a);image=lines[a:b]
        for edit in (lambda s:s.__setitem__(2,'VMM_NAME 00'),lambda s:s.__setitem__(-1,'VMM_END 2'),lambda s:s.__setitem__(0,'VMM_BEGIN 1 -1')):
            bad=list(image);edit(bad)
            with self.assertRaises(ValueError):parse(bad)
        duplicate=image[:-1]+image[1:-1]+['VMM_END 2']
        with self.assertRaisesRegex(ValueError,'Duplicate memory identity'):parse(duplicate)

if __name__=='__main__':unittest.main()
