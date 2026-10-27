import json,shutil,tempfile,unittest
from pathlib import Path
from resolver_growth import review,HERE

class ResolverGrowth(unittest.TestCase):
    root=HERE/'reports/resolver-growth'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def altered(self,edit):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'enabled.stdout';p.write_text(edit(p.read_text()))
            with self.assertRaises(ValueError):review(root)
    def test_new_constructor_cache_required(self):
        def edit(text):
            lines=text.splitlines();start=lines.index('RSM_API 1 1 0')
            i=next(i for i in range(start,len(lines)) if lines[i].startswith('VRS_SLOT 1 '));lines[i]='VRS_SLOT 1 1 00'
            return '\n'.join(lines)+'\n'
        self.altered(edit)
    def test_old_allocation_cannot_disappear(self):
        def edit(text):
            lines=text.splitlines();start=lines.index('RSM_API 1 1 0')
            i=next(i for i in range(start,len(lines)) if lines[i].startswith('VRS_NODE '));del lines[i:i+2]
            return '\n'.join(lines)+'\n'
        self.altered(edit)
    def test_original_runtime_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'baseline.stdout';s=p.read_text();self.assertIn('RES_VALUE 1 0 66',s);p.write_text(s.replace('RES_VALUE 1 0 66','RES_VALUE 1 0 ee',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
