"""Known base caches do not admit subclasses with extra private state."""
import json,shutil,tempfile,unittest
from pathlib import Path
import gate_family_probe as gate
ROOT=Path(__file__).resolve().parent/'reports/gate-families'

class GateFamilies(unittest.TestCase):
    def test_retained(self):
        result=gate.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(set(result['unsupportedProfilesRefused']),set(gate.FAMILIES))
    def mutate(self,filename,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr','.types') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/filename;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):gate.review(root)
    def test_partial_inventory_rejected(self):
        self.mutate('derived-boolean-observe.stdout',lambda s:s+'VGL_BEGIN 1 0\n','partial inventory')
    def test_native_type_evidence_required(self):
        self.mutate('derived-unary.types',lambda s:s.replace('8ExtraBuf','14vvp_fun_signal'),'Missing unsupported')
    def test_extra_state_behavior_preserved(self):
        self.mutate('derived-boolean-disabled.stdout',lambda s:s.replace('FAMILY_VALUE 1000 1 1','FAMILY_VALUE 1000 1 0'),'continuation')

if __name__=='__main__':unittest.main()
