import json,shutil,tempfile,unittest
from pathlib import Path
from concat_delta_family import review,HERE

class CompactConcatFamilies(unittest.TestCase):
    root=HERE/'reports/concat-delta-families'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def rejected(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_compact_output_rejected(self):
        self.rejected('derived4-late-observe.stdout','CCD_REFUSED 1','CCD_REFUSED 1\nVCD_BEGIN D 1000 1 0 0')
    def test_late_refusal_required(self):
        self.rejected('derived8-late-observe.stdout','CCD_REFUSED 3','CCD_REFUSED 4')
    def test_reference_admission_required(self):
        self.rejected('derived8-late-observe.stdout','CCD_REFERENCE','CCD_DELTA')
    def test_original_continuation_required(self):
        self.rejected('derived8-early-baseline.stdout','CONCAT_VALUE 1000 foreign 1','CONCAT_VALUE 1000 foreign 0')

if __name__=='__main__':unittest.main()
