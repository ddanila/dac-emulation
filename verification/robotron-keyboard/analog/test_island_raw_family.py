import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_family import review,HERE
ROOT=HERE/'reports/island-raw-families'

class IslandRawFamilies(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def reject(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/file;text=p.read_text();self.assertIn(old,text);p.write_text(text.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_inventory_rejected(self):
        self.reject('island-early-observe.stdout','RAW_REFUSED 0','RAW_REFUSED 0\nVIR_BEGIN 1 0')
    def test_prior_admission_required(self):
        self.reject('branch-late-observe.stdout','RAW_ADMITTED 0','RAW_REFUSED 0')
    def test_native_subclass_identity_required(self):
        self.reject('port-late-observe.stdout','9ExtraPort','15vvp_island_port')
    def test_private_island_state_required(self):
        self.reject('island-early-baseline.stdout','PRIVATE_RUN 2','PRIVATE_RUN 1')
    def test_original_continuation_required(self):
        self.reject('branch-late-baseline.stdout','VALUE 1000 foreign 1','VALUE 1000 foreign 0')

if __name__=='__main__':unittest.main()
