import json,shutil,tempfile,unittest
from pathlib import Path
from resolver_delta_family import review,HERE

class CompactResolverFamilies(unittest.TestCase):
    root=HERE/'reports/resolver-delta-families'
    def test_retained_native_replay(self):
        self.assertEqual(review(self.root),json.loads((self.root/'assessment.json').read_text()))
    def rejected(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(self.root,root)
            p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_partial_compact_output_rejected(self):
        self.rejected('derived-tri-late-observe.stdout','RCD_REFUSED 1','RCD_REFUSED 1\nVRX_BEGIN D 1000 1 0')
    def test_late_refusal_required(self):
        self.rejected('derived-extend-late-observe.stdout','RCD_REFUSED 3','RCD_REFUSED 4')
    def test_reference_admission_required(self):
        self.rejected('derived-extend-late-observe.stdout','RCD_REFERENCE','RCD_DELTA')
    def test_original_continuation_required(self):
        self.rejected('derived-extend-early-baseline.stdout','RESOLVER_VALUE 1000 foreign 1','RESOLVER_VALUE 1000 foreign 0')

    def test_wired_family_partial_output_rejected(self):
        for family in ('triand','trior'):
            with self.subTest(family=family):
                self.rejected(family+'-early-observe.stdout','RCD_REFUSED 0','RCD_REFUSED 0\nVRX_BEGIN R 0 1 1')
    def test_native_class_evidence_required(self):
        self.rejected('triand-late-1.types','13resolv_triand','10resolv_tri')

if __name__=='__main__':unittest.main()
