import copy,json,shutil,tempfile,unittest
from pathlib import Path
from concat_probe import review,parse,changed,HERE

class ConcatControls(unittest.TestCase):
    root=HERE/'reports/concat-state'
    def frame(self):
        lines=(self.root/'corrupt.stdout').read_text().splitlines();start=lines.index('CNM_BEFORE')+1;end=next(i for i in range(start,len(lines)) if lines[i].startswith('VCN_END '))+1
        return parse(lines[start:end])
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def test_raw_collision_is_not_logical_equivalence(self):
        before=self.frame();after=copy.deepcopy(before);n=after['nodes'][1];n['bits']='88'+n['bits'][2:]
        changed(before,after,n['id'],6)
        after['nodes'][0]['widths'][0]^=1
        with self.assertRaises(ValueError):changed(before,after,n['id'],6)
    def test_pending_binding_and_cache_changes_are_distinct(self):
        before=self.frame();after=copy.deepcopy(before);n=after['nodes'][0];n['widths'][2]^=1
        changed(before,after,n['id'],3)
        after['nodes'][1]['bits']='ee'+after['nodes'][1]['bits'][2:]
        with self.assertRaises(ValueError):changed(before,after,n['id'],3)
    def test_original_runtime_oracle_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'baseline.stdout';s=p.read_text();s=s.replace('CONCAT_VALUE 1000 0 1','CONCAT_VALUE 1000 0 0',1);p.write_text(s)
            with self.assertRaises(ValueError):review(root)
    def test_missing_executing_wrapper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'enabled.stdout';s=p.read_text();self.assertIn(' executing ',s);p.write_text(s.replace(' executing ',' active ',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
