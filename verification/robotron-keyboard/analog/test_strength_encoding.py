import json,shutil,tempfile,unittest
from pathlib import Path
import strength_encoding_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/strength-encoding'

class StrengthEncoding(unittest.TestCase):
    def test_retained_counterexample(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertFalse(result['tripletsInjectiveOnConstructorResolutionClosure'])
        self.assertEqual(result['collisions'],[dict(rawBytes=[0,136],triplet=[2,0,0],scalarEqual=False,vectorEqual=False)])
    def mutate(self,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            for mode in ('baseline','candidate'):
                p=root/(mode+'.stdout');p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_missing_native_equality_evidence(self):
        self.mutate(lambda s:s.replace('STRENGTH_COLLISION 0 136 0 0\n',''),'Missing collision')
    def test_truncated_resolution_closure(self):
        self.mutate(lambda s:s.replace('STRENGTH_RESOLVE 0 0 0\n',''),'Incomplete finite')
    def test_false_equality_rejected(self):
        self.mutate(lambda s:s.replace('STRENGTH_COLLISION 0 136 0 0','STRENGTH_COLLISION 0 136 1 1'),'Invalid native equality')

if __name__=='__main__':unittest.main()
