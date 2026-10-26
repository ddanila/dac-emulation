import copy,tempfile,unittest
from pathlib import Path
from island_filter_probe import review,parse_snapshot,fixture_state,changed_snapshot
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'reports/island-filter'

class IslandFilterProbe(unittest.TestCase):
    def snapshots(self):
        lines=(SOURCE/'enabled.stdout').read_text().splitlines();result=[]
        for i,line in enumerate(lines):
            if line!='VFM_BEFORE':continue
            end=next(j for j in range(i+1,len(lines)) if lines[j].startswith('VIF_END '))
            result.append(parse_snapshot(lines[i+1:end+1]))
        return result

    def test_runtime_force_release_controls(self):
        r=review(SOURCE);self.assertEqual(r['restoredFaults'],55)
        for i,s in enumerate(self.snapshots()):fixture_state(s,i)

    def test_partial_release_link_and_side_effect_rejected(self):
        shots=self.snapshots()
        bad=copy.deepcopy(shots[3]);bad['ports'][0]['mask']['bits']='1111'
        with self.assertRaises(ValueError):fixture_state(bad,3)
        bad=copy.deepcopy(shots[6]);bad['ports'][0]['link']['source']=1
        with self.assertRaises(ValueError):fixture_state(bad,6)
        before=shots[4];bad=copy.deepcopy(before);bad['ports'][0]['link']['destinationPort']=1
        changed_snapshot(before,bad,5)
        bad['ports'][1]['init']=1
        with self.assertRaises(ValueError):changed_snapshot(before,bad,5)

    def test_missing_fault_malformed_vector_and_output_rejected(self):
        for old,new in [('VFM_FAULT 3 1 1','VFM_FAULT 3 0 1'),('VIF_VECTOR forced 0 -','VIF_VECTOR forced 1 -'),('CHANGE 6000 1010 1010','CHANGE 6000 1100 1100')]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)
                for mode in ('baseline','disabled','enabled','corrupt'):
                    for suffix in ('stdout','stderr'):
                        text=(SOURCE/(mode+'.'+suffix)).read_text()
                        if mode=='corrupt':text=text.replace(old,new,1)
                        (root/(mode+'.'+suffix)).write_text(text)
                with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
