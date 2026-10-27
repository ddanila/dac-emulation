"""Compact references must not admit unsupported later filter allocations."""
import json,shutil,tempfile,unittest
from pathlib import Path
import wire_raw_delta_family as probe
ROOT=Path(__file__).resolve().parent/'reports/wire-raw-delta-families'

class RawDeltaFamilies(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def mutate(self,filename,change,pattern):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr','.types') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/filename;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_partial_delta_output_rejected(self):
        self.mutate('derived8-late-observe.stdout',lambda s:s.replace('WRC_REFUSED 1','WRC_REFUSED 1\nVWC_BEGIN D 1000 1 0\nVWC_END 0'),'partial inventory')
    def test_missing_late_refusal(self):
        self.mutate('real-late-observe.stdout',lambda s:s.replace('WRC_REFUSED 3\n',''),'Missing compact')
    def test_initial_dense_reference_agreement(self):
        self.mutate('derived4-late-observe.stdout',lambda s:s.replace('VWC_BEGIN R 0','VWC_BEGIN R 1'),'differs from native')

if __name__=='__main__':unittest.main()
