import copy,json,shutil,tempfile,unittest
from resolver_probe import review,parse,changed,tree,HERE

class ResolverControls(unittest.TestCase):
    root=HERE/'reports/resolver-state'
    def frame(self,marker='RSM_BEFORE'):
        lines=(self.root/'corrupt.stdout').read_text().splitlines();i=lines.index(marker)+1;j=next(j for j in range(i,len(lines)) if lines[j].startswith('VRS_END '))+1
        return parse(lines[i:j])
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_pointer_fault_retains_safe_allocation(self):
        before=self.frame();node=before['nodes'][0];after=self.frame(f"RSM_CHANGED {node['id']} 5 0")
        changed(before,after,node['id'],5,0)
        target=after['nodes'][0];self.assertEqual(target['values'],0);self.assertEqual(target['allocation'],node['allocation']);self.assertEqual(target['vectors'],node['vectors'])
    def test_port_fault_does_not_resize_observed_storage(self):
        before=self.frame();node=before['nodes'][0];after=self.frame(f"RSM_CHANGED {node['id']} 2 0")
        changed(before,after,node['id'],2,0);self.assertEqual(after['nodes'][0]['slots'],node['slots'])
        after['nodes'][0]['pull']^=1
        with self.assertRaisesRegex(ValueError,'unrelated'):changed(before,after,node['id'],2,0)
    def test_resolution_oracle_conflict_and_pull(self):
        zero=bytes([0x66]*9);one=bytes([0xee]*9);z=bytes(9)
        self.assertEqual(tree([zero,one],0)[-1],bytes([0xe6]*9))
        self.assertEqual(tree([z,z],0x55)[-1],bytes([0x55]*9))
        self.assertEqual(tree([one,z],0x55)[-1],one)
        self.assertEqual(tree([b'']*17,0xdd),[b'']*25)
    def test_original_runtime_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'baseline.stdout';s=p.read_text();self.assertIn('RES_VALUE 1 0 66',s);p.write_text(s.replace('RES_VALUE 1 0 66','RES_VALUE 1 0 ee',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
