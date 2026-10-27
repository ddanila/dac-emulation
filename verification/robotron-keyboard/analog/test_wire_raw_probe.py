import json,shutil,tempfile,unittest
from pathlib import Path
import wire_raw_probe as probe
ROOT=Path(__file__).resolve().parent/'reports/wire-raw-state'

class WireRawProbe(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(probe.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_collision_remains_distinct(self):
        self.assertEqual(probe.triplet(0),probe.triplet(136))
        state=probe.parse(['VWB_BEGIN 1 0','VWB_FILTER 1 0x10 0x20 2 0088 0 -','VWB_END 1'])
        self.assertEqual(state['filters'][0]['vectors'][0],bytes([0,136]))
    def mutate(self,change,pattern):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'enabled.stdout';p.write_text(change(p.read_text()))
            with self.assertRaisesRegex(ValueError,pattern):probe.review(root)
    def test_normalization_loses_evidence(self):
        def collapse(text):
            lines=text.splitlines()
            for i,line in enumerate(lines):
                if line.startswith('VWB_FILTER '):
                    row=line.split()
                    for col in (5,7):
                        if row[col]!='-':row[col]=bytes(0 if b==136 else b for b in bytes.fromhex(row[col])).hex()
                    lines[i]=' '.join(row)
            return '\n'.join(lines)+'\n'
        self.mutate(collapse,'stimulus')
    def test_malformed_byte_length(self):
        with self.assertRaisesRegex(ValueError,'raw vector'):
            probe.parse(['VWB_BEGIN 1 0','VWB_FILTER 1 0x10 0x20 2 88 0 -','VWB_END 1'])

if __name__=='__main__':unittest.main()
