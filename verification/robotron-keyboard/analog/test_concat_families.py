import json,shutil,tempfile,unittest
from pathlib import Path
from concat_family_probe import review,HERE

class ConcatFamilies(unittest.TestCase):
    root=HERE/'reports/concat-families'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def rejected(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_inventory_refused(self):
        self.rejected('derived4-early-observe.stdout','CONCAT_REFUSED 0','CONCAT_REFUSED 0\nVCN_BEGIN 1 0')
    def test_late_prior_inventory_required(self):
        self.rejected('derived8-late-observe.stdout','CONCAT_ADMITTED 0','CONCAT_REFUSED 0')
    def test_native_class_evidence_required(self):
        self.rejected('derived4-late-1.types','12ExtraConcat4','15vvp_fun_concat8')
    def test_original_continuation_required(self):
        self.rejected('derived8-late-baseline.stdout','CONCAT_VALUE 1000 foreign 1','CONCAT_VALUE 1000 foreign 0')

if __name__=='__main__':unittest.main()
