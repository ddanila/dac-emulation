import json,shutil,tempfile,unittest
from pathlib import Path
from concat_growth import review,HERE

class ConcatGrowth(unittest.TestCase):
    root=HERE/'reports/concat-growth'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def altered(self,edit):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'enabled.stdout';p.write_text(edit(p.read_text()))
            with self.assertRaises(ValueError):review(root)
    def test_new_constructor_storage_required(self):
        def edit(text):
            lines=text.splitlines()
            i=next(i for i,l in enumerate(lines) if l.startswith('VCN_NODE ') and l.split()[11]=='98')
            a=lines[i].split();a[12]='1'+a[12][1:];lines[i]=' '.join(a)
            return '\n'.join(lines)+'\n'
        self.altered(edit)
    def test_old_allocation_cannot_disappear(self):
        def edit(text):
            lines=text.splitlines();start=lines.index('CNM_API 1 1 0')
            i=next(i for i in range(start,len(lines)) if lines[i].startswith('VCN_NODE '));del lines[i]
            return '\n'.join(lines)+'\n'
        self.altered(edit)
    def test_original_runtime_continuation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/'baseline.stdout';s=p.read_text();self.assertIn('CONCAT_VALUE 1000 0 1',s);p.write_text(s.replace('CONCAT_VALUE 1000 0 1','CONCAT_VALUE 1000 0 0',1))
            with self.assertRaises(ValueError):review(root)

if __name__=='__main__':unittest.main()
