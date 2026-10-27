"""Native filters created after reference initialization require complete new rows."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
import wire_raw_growth as growth
import wire_raw_delta_probe as delta
ROOT=Path(__file__).resolve().parent/'reports/wire-raw-growth'

class RawWireGrowth(unittest.TestCase):
    def frames(self):
        lines=(ROOT/'corrupt.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VWC_BEGIN '):frame,i=delta.block(lines,i);frames.append(frame)
            else:i+=1
        return frames
    def test_retained(self):
        r=growth.review(ROOT);self.assertEqual(r,json.loads((ROOT/'assessment.json').read_text()))
        self.assertTrue(r['nativePostReferenceAllocation'])
    def test_new_native_rows_are_complete(self):
        frames=self.frames();reference=frames[0]['rows'];self.assertEqual(len(reference),1)
        later=[f for f in frames[1:] if f['total']==5];self.assertTrue(later)
        for frame in later:
            new={k:v for k,v in frame['rows'].items() if k not in reference};self.assertEqual(len(new),4)
            self.assertTrue(all(prefix==suffix==0 for prefix,suffix,_ in new.values()))
            delta.reconstruct(reference,frame)
    def test_missing_new_row_rejected(self):
        frames=self.frames();reference=frames[0]['rows'];frame=copy.deepcopy(next(f for f in frames[1:] if f['total']==5))
        del frame['rows'][next(k for k in frame['rows'] if k not in reference)]
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(reference,frame)
    def test_native_continuation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for p in ROOT.iterdir():
                if p.suffix in ('.stdout','.stderr') or p.name=='run.json':shutil.copy2(p,root/p.name)
            p=root/'baseline.stdout';s=p.read_text();p.write_text(s.replace('WIRE_RAW_VALUE 1 4 ','LOST_VALUE 1 4 '))
            with self.assertRaisesRegex(ValueError,'continuation'):growth.review(root)

if __name__=='__main__':unittest.main()
