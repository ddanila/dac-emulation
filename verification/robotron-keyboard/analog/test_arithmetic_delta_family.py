import json,shutil,tempfile,unittest
from pathlib import Path
import arithmetic_delta_family as probe
ROOT=Path(__file__).resolve().parent/'reports/arithmetic-delta-families'

class ArithmeticLateFamily(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def mutate(self,filename,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr','.types','.reference') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/filename;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_reference_must_precede_unknown_family(self):
        self.mutate('derived.reference',lambda s:s.replace('VAD_BEGIN R 0','VAD_BEGIN R 1'),'Invalid admitted reference')
    def test_partial_delta_rejected(self):
        self.mutate('division-observe.stdout',lambda s:s+'VAD_BEGIN D 0 2 1\n','partial inventory')
    def test_native_unknown_class_required(self):
        self.mutate('derived.types',lambda s:s.replace('8ExtraSum','8NotASumX'),'Missing unsupported')

if __name__=='__main__':unittest.main()
