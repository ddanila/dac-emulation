import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_partselect import review,HERE,output_text,resolved
ROOT=HERE/'reports/island-raw-partselect'

class IslandRawPartselect(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_high_offset_only_changes_connected_slice(self):
        a,b=resolved((0x66,0xee),(80,9,63))
        self.assertEqual(a,bytes([0x66]*63+[0xe6]*9+[0x66]*8));self.assertEqual(b,bytes([0xe6]*9))
    def test_low_offset_preserves_upper_bits(self):
        a,b=resolved((0x66,0xee),(80,8,0))
        self.assertEqual(a,bytes([0xe6]*8+[0x66]*72))
    def test_partselect_does_not_apply_switch_attenuation(self):
        a,b=resolved((0xff,0x66),(9,1,8));self.assertEqual(a,bytes([0xff]*9));self.assertEqual(b,b'\xff')
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);s=output_text(root,mode);self.assertIn(old,s);(root/(mode+'.stdout')).write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_original_narrow_output_required(self):
        self.reject('baseline','GROW_VALUE 1000 0 e6','GROW_VALUE 1000 0 ee')
    def test_branch_offset_required(self):
        self.reject('enabled','VI_TRAN 0x0 9 1 8 1 0 1','VI_TRAN 0x0 9 1 7 1 0 1')
    def test_wide_cache_bits_required(self):
        self.reject('enabled','VIR_VECTOR 1 80 '+('66'*63)+('e6'*9)+('66'*8),'VIR_VECTOR 1 80 '+('66'*80))
    def test_targeted_narrow_fault_required(self):
        self.reject('corrupt','IRM_CHANGED 4 2 0 2','IRM_CHANGED 4 1 0 2')
    def test_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
