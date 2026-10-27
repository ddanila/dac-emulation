import json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_delta_family import review,HERE
ROOT=HERE/'reports/island-raw-delta-families'

class IslandRawDeltaFamilies(unittest.TestCase):
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def reject(self,file,old,new):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'report';shutil.copytree(ROOT,root);p=root/file;s=p.read_text();self.assertIn(old,s);p.write_text(s.replace(old,new,1))
            with self.assertRaises(ValueError):review(root)
    def test_delta_requires_reference(self):
        self.reject('island-late-observe.stdout','IX_REFUSED NOREF 0','IX_REFUSED NOREF 1')
    def test_reference_cannot_reset(self):
        self.reject('branch-late-observe.stdout','IX_REFUSED DUPLICATE 0','IX_ADMITTED DUPLICATE 0')
    def test_initial_reference_refusal_required(self):
        self.reject('port-early-observe.stdout','IX_REFUSED R 0','IX_REFUSED D 0')
    def test_late_delta_refusal_required(self):
        self.reject('island-late-observe.stdout','IX_REFUSED D 4','IX_REFUSED D 3')
    def test_partial_output_rejected(self):
        self.reject('port-early-observe.stdout','IX_REFUSED D 0','VIX_BEGIN D 0 1 0\nVIX_END 0\nIX_REFUSED D 0')
    def test_prior_delta_population_required(self):
        self.reject('branch-late-observe.stdout','VIX_BEGIN D 0 1 0','VIX_BEGIN D 0 2 0')
    def test_original_private_behavior_required(self):
        self.reject('island-late-baseline.stdout','PRIVATE_RUN 2','PRIVATE_RUN 1')

if __name__=='__main__':unittest.main()
