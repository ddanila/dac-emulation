import json,shutil,tempfile,unittest
from pathlib import Path
from resolver_family_probe import review,HERE

class ResolverFamilies(unittest.TestCase):
    root=HERE/'reports/resolver-families'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def rejected(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_inventory_refused(self):
        self.rejected('derived-tri-early-observe.stdout','RESOLVER_REFUSED 0','RESOLVER_REFUSED 0\nVRS_BEGIN 1 0')
    def test_prior_valid_inventory_required(self):
        self.rejected('derived-extend-late-observe.stdout','RESOLVER_ADMITTED 0','RESOLVER_REFUSED 0')
    def test_native_class_evidence_required(self):
        self.rejected('triand-late-1.types','13resolv_triand','10resolv_tri')
    def test_original_continuation_required(self):
        self.rejected('derived-extend-late-baseline.stdout','RESOLVER_VALUE 1000 foreign 1','RESOLVER_VALUE 1000 foreign 0')

if __name__=='__main__':unittest.main()
