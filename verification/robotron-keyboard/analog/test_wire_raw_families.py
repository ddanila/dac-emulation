"""Reject unsupported filters before output, including post-admission allocations."""
import json,shutil,tempfile,unittest
from pathlib import Path
import wire_raw_family_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/wire-raw-families'

class RawWireFamilies(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def mutate(self,filename,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr','.types') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/filename;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_partial_output_after_late_allocation(self):
        self.mutate('derived8-late-observe.stdout',lambda s:s.replace('RAW_REFUSED 1','VWB_BEGIN 1 1000\nRAW_REFUSED 1'),'partial inventory')
    def test_private_behavior_preserved(self):
        self.mutate('derived4-early-observe.stdout',lambda s:s.replace('RAW_VALUE 1 foreign 1','RAW_VALUE 1 foreign 0'),'continuation')
    def test_late_class_evidence_required(self):
        self.mutate('derived8-late-1.types',lambda s:s.replace('ExtraWire8','OtherWire8'),'class evidence')
    def test_initial_reference_is_required(self):
        self.mutate('real-late-observe.stdout',lambda s:s.replace('RAW_ADMITTED 0','RAW_REFUSED 0'),'initial admitted')

if __name__=='__main__':unittest.main()
