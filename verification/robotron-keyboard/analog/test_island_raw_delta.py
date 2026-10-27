import copy,json,shutil,tempfile,unittest
from pathlib import Path
from island_raw_delta import HERE,review,review_case,output_text,block,reconstruct,separate
ROOT=HERE/'reports/island-raw-delta'

class IslandRawDelta(unittest.TestCase):
    def frames(self):
        lines=output_text(ROOT/'growth_callbacks','enabled').splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VIX_BEGIN '):
                frame,i=block(lines,i);frames.append(frame)
            else:i+=1
        return frames
    def test_retained_native_replay(self):
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
    def test_growth_requires_full_new_rows(self):
        frames=self.frames();reference=frames[0]['rows'];frame=copy.deepcopy(next(f for f in frames[1:] if f['total']>len(reference)))
        identity=next(i for i in frame['rows'] if i not in reference);self.assertEqual(frame['rows'][identity][:2],(0,0));del frame['rows'][identity]
        with self.assertRaises(ValueError):reconstruct(reference,frame)
    def test_reference_is_immutable(self):
        frames=self.frames();reference=frames[0]['rows'];saved=copy.deepcopy(reference)
        for f in frames[1:]:reconstruct(reference,f)
        self.assertEqual(reference,saved)
    def test_splice_bounds_checked(self):
        frames=self.frames();reference=frames[0]['rows'];frame=copy.deepcopy(next(f for f in frames[1:] if f['rows']))
        identity=next(iter(frame['rows']));frame['rows'][identity]=(len(reference.get(identity,''))+1,0,'')
        with self.assertRaises(ValueError):reconstruct(reference,frame)
    def test_dense_delta_pair_required(self):
        lines=output_text(ROOT/'growth_callbacks','enabled').splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VIX_BEGIN D '));_,end=block(lines,start)
        with self.assertRaises(ValueError):separate(lines[:start]+lines[end:])
    def test_reference_required(self):
        lines=output_text(ROOT/'growth_callbacks','enabled').splitlines();start=next(i for i,l in enumerate(lines) if l.startswith('VIX_BEGIN R '));_,end=block(lines,start)
        with self.assertRaises(ValueError):separate(lines[:start]+lines[end:])
    def test_original_intermediate_output_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'feedback';shutil.copytree(ROOT/'feedback',root);text=output_text(root,'baseline');old='GROW_VALUE 2000 0 ee\n';self.assertIn(old,text)
            (root/'baseline.stdout').write_text(text.replace(old,'',1))
            with self.assertRaises(ValueError):review_case(root,'feedback')

if __name__=='__main__':unittest.main()
