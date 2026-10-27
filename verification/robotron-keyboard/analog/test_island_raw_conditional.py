import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_conditional import review,HERE,output_text,resolved,transmitted,branch_state
ROOT=HERE/'reports/island-raw-conditional'

class IslandRawConditional(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_unknown_and_enabled_maps_match_original_helper(self):
        seen=set()
        for line in (HERE/'reports/strength-switch/baseline.stdout').read_text().splitlines():
            if not line.startswith('SW_RESULT '):continue
            resistive,unknown,left,right,result=map(int,line.split()[1:])
            if left:continue
            self.assertEqual(transmitted(right,bool(resistive),bool(unknown)),result);seen.add((resistive,unknown,right))
        self.assertEqual(len(seen),4*127)
    def test_polarity_and_unknown_controls(self):
        self.assertEqual([branch_state(p,0) for p in range(1,5)],[1,0,2,2])
        self.assertEqual([branch_state(p,2) for p in range(1,5)],[0,1,2,2])
    def test_disabled_branch_isolates_drivers(self):
        self.assertEqual(resolved((0x66,0xee),False,0),(0x66,0xee))
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);s=output_text(root,mode);self.assertIn(old,s);(root/(mode+'.stdout')).write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_original_unknown_output_required(self):
        self.reject('baseline','GROW_VALUE 3000 4 d5','GROW_VALUE 3000 4 ee')
    def test_imported_enable_cache_required(self):
        self.reject('enabled','VIR_VECTOR 0 1 e6','VIR_VECTOR 0 1 ee')
    def test_control_polarity_required(self):
        text=output_text(ROOT,'enabled');line=next(l for l in text.splitlines() if l.startswith('VI_TRAN '));parts=line.split();parts[5]='1'
        self.reject('enabled',line,' '.join(parts))
    def test_enable_port_fault_required(self):
        self.reject('corrupt','IRM_CHANGED 8 3 0 2','IRM_CHANGED 8 2 0 2')
    def test_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
