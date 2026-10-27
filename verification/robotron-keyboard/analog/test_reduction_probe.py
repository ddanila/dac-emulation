import json,shutil,tempfile,unittest
from pathlib import Path
import reduction_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/reduction-state'

class ReductionProbe(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def mutate(self,name,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/name;p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_partial_cannot_discard_history(self):
        self.mutate('enabled.stdout',lambda s:s.replace('0'*71+'1'+'0'*8,'3'*71+'1'+'3'*8),'stimulus oracle')
    def test_empty_and_unknown_oracle(self):
        self.assertEqual(''.join(probe.output(i,'') for i in range(1,7)),'100011')
        self.assertEqual(''.join(probe.output(i,'02') for i in range(1,7)),'033133')
        self.assertEqual(''.join(probe.output(i,'13') for i in range(1,7)),'313303')
    def test_restoration_required(self):
        self.mutate('corrupt.stdout',lambda s:s.replace('RDM_RESTORED','RDM_MISSING',1),'Expected RDM_RESTORED')
    def test_malformed_operand_rejected(self):
        for row in ('VRD_NODE 1 0x10 0x20 7 0 -','VRD_NODE 1 0x10 0x20 1 1 -','VRD_NODE 1 0x10 0x20 1 1 4'):
            with self.subTest(row=row),self.assertRaises(ValueError):probe.parse(['VRD_BEGIN 1 0',row,'VRD_END 1'])

if __name__=='__main__':unittest.main()
