import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_strengths import review,HERE,INPUTS,output_text,resolved,transmitted
from resolver_strength_oracle import scalar
ROOT=HERE/'reports/island-raw-strengths'

class IslandRawStrengths(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_transmission_matches_original_helper_domain(self):
        seen=set()
        for line in (HERE/'reports/strength-switch/baseline.stdout').read_text().splitlines():
            if line.startswith('SW_RESULT 0 0 0 '):
                _,resistive,unknown,left,right,result=line.split();right=int(right)
                self.assertEqual(transmitted(right),int(result));seen.add(right)
        self.assertTrue(set(INPUTS)<=seen)
    def test_scalar_matches_all_original_pairs(self):
        count=0
        for line in (HERE/'reports/strength-encoding/baseline.stdout').read_text().splitlines():
            if line.startswith('STRENGTH_RESOLVE '):
                a,b,result=map(int,line.split()[1:]);self.assertEqual(scalar(a,b),result);count+=1
        self.assertEqual(count,127**2)
    def test_supply_is_limited_only_after_transmission(self):
        self.assertEqual(resolved(0xff),(0xff,0xee))
        self.assertEqual(resolved(0x77),(0x77,0x66))
    def test_high_impedance_encodings_resolve_equally(self):
        self.assertEqual(resolved(0x88),(0,0));self.assertEqual(resolved(0),(0,0))
    def reject(self,mode,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);s=output_text(root,mode);self.assertIn(old,s);(root/(mode+'.stdout')).write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_original_output_required(self):
        self.reject('baseline','GROW_VALUE 10000 0 ee','GROW_VALUE 10000 0 ff')
    def test_raw_hiz_cache_required(self):
        self.reject('enabled','VIR_VECTOR 0 80 '+('88'*80),'VIR_VECTOR 0 80 '+('00'*80))
    def test_no_spurious_repeated_output(self):
        self.reject('baseline','GROW_PHASE 16','GROW_PHASE 16\nGROW_VALUE 16000 0 00')
    def test_fault_restoration_required(self):
        self.reject('corrupt','IRM_RESTORED','IRM_CHANGED')

if __name__=='__main__':unittest.main()
