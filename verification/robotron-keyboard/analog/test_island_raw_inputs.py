import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_inputs import review,HERE,expected_input
ROOT=HERE/'reports/island-raw-inputs'

class IslandRawInputs(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def reject(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_merge_keeps_distant_bit(self):
        self.assertEqual(expected_input(2,9),bytes([0x66]+[0]*7+[0xee]))
    def test_weak_partial_keeps_untouched_bits(self):
        self.assertEqual(expected_input(4,8),bytes([0x33]*7+[0xbb]))
    def test_original_output_checked(self):
        self.reject('baseline.stdout','GROW_VALUE 4000 0 bb','GROW_VALUE 4000 0 ee')
    def test_repeated_partial_must_not_emit(self):
        self.reject('baseline.stdout','GROW_PHASE 5','GROW_PHASE 5\nGROW_VALUE 5000 0 bb')
    def test_full_cache_required(self):
        self.reject('enabled.stdout','VIR_VECTOR 0 80 '+('33'*80),'VIR_VECTOR 0 80 '+('33'*79)+'66')
    def test_fault_target_required(self):
        self.reject('corrupt.stdout','IRM_CHANGED 4 2 0 2','IRM_CHANGED 3 2 0 2')
    def test_restoration_required(self):
        self.reject('corrupt.stdout','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
