"""Post-reference native allocations must remain complete and correctly bound."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
import mux_growth_probe as growth
import mux_delta_probe as delta
ROOT=Path(__file__).resolve().parent/'reports/mux-growth'

class MuxGrowth(unittest.TestCase):
    def test_retained(self):
        result=growth.review(ROOT)
        self.assertEqual(result,json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(result['nativeAllocationGrowth'],[1,2,3])
        self.assertEqual(result['newMuxPendingFaultWidths'],[3,80])
    def test_missing_new_native_record(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines();ref=None;i=0
        while i<len(lines):
            if lines[i].startswith('VXD_BEGIN '):
                frame,i=delta.block(lines,i)
                if frame['mode']=='R':ref=frame['rows']
                elif frame['total']>len(ref):break
            else:i+=1
        self.assertIsNotNone(ref)
        new=set(frame['rows'])-set(ref);self.assertTrue(new)
        damaged=copy.deepcopy(frame);damaged['rows'].pop(next(iter(new)))
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(ref,damaged)
    def test_missing_late_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'baseline.stdout';p.write_text(p.read_text().replace('GROW_VALUE 4000 3 111\n',''))
            with self.assertRaisesRegex(ValueError,'oracle'):growth.review(root)
    def test_changed_live_identity(self):
        # Work on decoded records so the binding guard is tested independently
        # of the dense-versus-delta guard.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            for p in root.glob('*.stdout'):
                lines,*_=delta.separate(p.read_text().splitlines())
                if p.name=='enabled.stdout':
                    tick=0
                    for i,line in enumerate(lines):
                        if line.startswith('VXM_BEGIN '):tick=int(line.split()[2])
                        if tick==5000 and line.startswith('VXM_MUX '):
                            row=line.split()
                            if row[8]=='80':row[3]='0x1234';lines[i]=' '.join(row)
                p.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError,'Live mux binding'):growth.dense_review(root)

if __name__=='__main__':unittest.main()
