import copy,json,shutil,tempfile,unittest
from pathlib import Path
import reduction_growth_probe as probe
from reduction_delta_probe import block,reconstruct,separate
ROOT=Path(__file__).resolve().parent/'reports/reduction-growth'

class ReductionGrowth(unittest.TestCase):
    def test_retained(self):
        result=probe.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(result['allocationGrowth'],[1,7])
    def test_new_native_rows_required(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VRE_BEGIN '):
                frame,i=block(lines,i);frames.append(frame)
            else:i+=1
        reference=frames[0]['rows'];self.assertEqual(len(reference),1)
        frame=copy.deepcopy(next(f for f in frames if f['total']==7))
        self.assertEqual(len(frame['rows']),6)
        self.assertTrue(all(prefix==suffix==0 for prefix,suffix,_ in frame['rows'].values()))
        frame['rows'].pop(next(iter(frame['rows'])))
        with self.assertRaisesRegex(ValueError,'Missing new'):reconstruct(reference,frame)
    def test_missing_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'disabled.stdout';p.write_text(p.read_text().replace('REDUCTION_VALUE 11000 5 3','REDUCTION_VALUE 11000 5 0'))
            with self.assertRaisesRegex(ValueError,'independent oracle'):probe.review(root)
    def test_live_binding_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            for p in root.glob('*.stdout'):
                lines,*_=separate(p.read_text().splitlines());p.write_text('\n'.join(lines)+'\n')
            p=root/'enabled.stdout';lines=p.read_text().splitlines()
            # Change both copies of the same live new object after construction.
            stage=0
            for i,line in enumerate(lines):
                if line.startswith('RDM_API '):stage=int(line.split()[1])
                if stage==2 and line.startswith('VRD_NODE '):
                    row=line.split()
                    if row[4]=='2':row[3]='0x123456789';lines[i]=' '.join(row)
            p.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError,'rebound'):probe.review_dense(root)

if __name__=='__main__':unittest.main()
