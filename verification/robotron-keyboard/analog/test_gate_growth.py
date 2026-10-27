"""Post-reference gate creation must retain complete caches and stable identities."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
import gate_growth_probe as growth
import gate_delta_probe as delta
ROOT=Path(__file__).resolve().parent/'reports/gate-growth'

class GateGrowth(unittest.TestCase):
    def test_retained(self):
        result=growth.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(result['nativeAllocationGrowth'],[1,9])
    def test_missing_new_native_record(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();reference=None;i=0
        while i<len(lines):
            if lines[i].startswith('VGD_BEGIN '):
                frame,i=delta.block(lines,i)
                if frame['mode']=='R':reference=frame['rows']
                elif frame['total']>len(reference):break
            else:i+=1
        self.assertEqual(len(reference),1)
        new=set(frame['rows'])-set(reference);self.assertEqual(len(new),8)
        damaged=copy.deepcopy(frame);damaged['rows'].pop(next(iter(new)))
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(reference,damaged)
    def test_live_binding_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            for p in root.glob('*.stdout'):
                lines,*_=delta.separate(p.read_text().splitlines())
                if p.name=='enabled.stdout':
                    tick=0
                    for i,line in enumerate(lines):
                        if line.startswith('VGL_BEGIN '):tick=int(line.split()[2])
                        if tick==5000 and line.startswith('VGL_GATE '):
                            row=line.split()
                            if row[5]=='5':row[3]='0x1234';lines[i]=' '.join(row)
                p.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError,'binding changed'):growth.dense_review(root)
    def test_missing_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'baseline.stdout';p.write_text(p.read_text().replace('GATE_VALUE 4000 7 '+'3'*80+'\n',''))
            with self.assertRaisesRegex(ValueError,'oracle'):growth.review(root)

if __name__=='__main__':unittest.main()
