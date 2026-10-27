import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_competing import review,HERE,INPUTS,output_text,resolved,transmitted
ROOT=HERE/'reports/island-raw-competing'

class IslandRawCompeting(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_both_transmission_maps_match_original_domain(self):
        seen=set()
        for line in (HERE/'reports/strength-switch/baseline.stdout').read_text().splitlines():
            if not line.startswith('SW_RESULT '):continue
            resistive,unknown,left,right,result=map(int,line.split()[1:])
            if unknown or left:continue
            self.assertEqual(transmitted(right,bool(resistive)),result);seen.add((resistive,right))
        self.assertEqual(len(seen),2*127)
        self.assertTrue({(r,v) for r in (0,1) for pair in INPUTS for v in pair}<=seen)
    def test_equal_opposite_strong_drivers(self):
        self.assertEqual(resolved((0x66,0xee),False),(0xe6,0xe6))
        self.assertEqual(resolved((0x66,0xee),True),(0x66,0xee))
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);s=output_text(root,mode);self.assertIn(old,s);(root/(mode+'.stdout')).write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_original_resistive_output_required(self):
        self.reject('baseline','GROW_VALUE 1000 4 ee','GROW_VALUE 1000 4 e6')
    def test_complete_resistive_cache_required(self):
        self.reject('enabled','VIR_VECTOR 0 80 '+('ee'*80),'VIR_VECTOR 0 80 '+('ee'*79)+'66')
    def test_repeated_input_must_not_emit(self):
        self.reject('baseline','GROW_PHASE 11','GROW_PHASE 11\nGROW_VALUE 11000 0 ee')
    def test_targeted_fault_required(self):
        self.reject('corrupt','IRM_CHANGED 8 2 0 2','IRM_CHANGED 7 2 0 2')
    def test_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
