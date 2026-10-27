import json,shutil,tempfile,unittest
from pathlib import Path
import strength_switch_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/strength-switch'

class StrengthSwitch(unittest.TestCase):
    def test_retained(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(result['switchOutputsRemainInConstructorResolutionClosure'])
        self.assertFalse(result['tripletsInjectiveOnConstructorResolutionClosure'])
    def mutate(self,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            for mode in ('baseline','candidate'):
                p=root/(mode+'.stdout');p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_missing_pair(self):
        self.mutate(lambda s:s.replace('SW_RESULT 0 0 0 0 0\n',''),'Incomplete switch')
    def test_wrong_raw_result(self):
        self.mutate(lambda s:s.replace('SW_RESULT 0 0 0 0 0','SW_RESULT 0 0 0 0 136'),'differs from native')
    def test_changed_strength_map(self):
        self.mutate(lambda s:s.replace('SW_MAP 1 0 1 1 2 2 3 5 5','SW_MAP 1 0 1 1 2 2 3 6 6'),'Changed pinned strength')

if __name__=='__main__':unittest.main()
