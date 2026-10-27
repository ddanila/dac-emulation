import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_growth_callbacks import review,HERE
ROOT=HERE/'reports/island-raw-growth-callbacks'

class IslandRawGrowthCallbacks(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def reject(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_constructor_observation_required(self):
        self.reject('enabled.stdout','IRM_STAGE 1 0 1','IRM_STAGE 2 0 1')
    def test_raw_constructor_value_checked(self):
        self.reject('enabled.stdout','VIR_VECTOR 0 0 -','VIR_VECTOR 0 1 66')
    def test_original_output_checked(self):
        self.reject('baseline.stdout','GROW_VALUE 2000 2 111111111','GROW_VALUE 2000 2 000000000')
    def test_fault_restoration_required(self):
        self.reject('corrupt.stdout','IRM_RESTORED','IRM_CHANGED')
    def test_complete_population_required(self):
        self.reject('enabled.stdout','VIR_END 3','VIR_END 2')
    def test_live_scratch_required(self):
        self.reject('enabled.stdout','VIR_VECTOR 2 1 66','VIR_VECTOR 2 0 -')
    def test_target_owner_required(self):
        self.reject('corrupt.stdout','IRM_CHANGED 3 2 2 0','IRM_CHANGED 2 2 2 0')
    def test_callback_boundary_required(self):
        self.reject('enabled.stdout','IRM_STAGE 6 2 1','IRM_STAGE 6 0 1')
    def test_lifetime_binding_required(self):
        self.reject('enabled.stdout','VIR_ISLAND 3 ','VIR_ISLAND 4 ')

if __name__=='__main__':unittest.main()
