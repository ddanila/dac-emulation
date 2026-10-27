"""Gate differences must reconstruct changed widths, faults and wrapper frames."""
import copy,json,unittest
from pathlib import Path
import gate_delta_probe as delta
import gate_delta_board as board
import gate_delta_family as families
HERE=Path(__file__).resolve().parent

class GateDelta(unittest.TestCase):
    def frames(self):
        lines=(HERE/'reports/gate-delta/enabled.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VGD_BEGIN '):frame,i=delta.block(lines,i);frames.append(frame)
            else:i+=1
        return frames
    def test_retained(self):
        for name,review in [('gate-delta',delta.review),('gate-input-delta',delta.review),('gate-delta-budget',board.review),('gate-delta-families',families.review)]:
            root=HERE/'reports'/name
            with self.subTest(name=name):self.assertEqual(review(root),json.loads((root/'assessment.json').read_text()))
    def test_new_allocation_and_invalid_splice(self):
        ref=self.frames()[0]['rows'];frame=dict(mode='D',tick=1,total=len(ref)+1,rows={},events=[])
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(ref,frame)
        row=next(iter(ref.values())).split();identity=max(ref)+1
        row[1]=str(identity);row[2]='0x110';row[3]='0x120';row[4]='0x128';row[7]='0x0'
        frame['rows'][identity]=(0,0,' '.join(row)+'\n')
        image=delta.reconstruct(ref,frame)
        self.assertEqual(delta.dense.parse(image)['gates'][-1]['id'],identity)
        frame['rows'][identity]=(1,0,'x')
        with self.assertRaisesRegex(ValueError,'exceeds reference'):delta.reconstruct(ref,frame)
    def test_complete_wrapper_frame(self):
        frames=self.frames();ref=frames[0]['rows'];queued=next(f for f in frames[1:] if any(' active ' in e for e in f['events']))
        state=delta.dense.parse(delta.reconstruct(ref,queued));delta.dense.validate(state)
        bad=copy.deepcopy(queued);bad['events']=[]
        other=delta.dense.parse(delta.reconstruct(ref,bad));self.assertFalse(other['events'])
        with self.assertRaisesRegex(ValueError,'queue mismatch'):delta.dense.validate(other)
    def test_missing_dense_pair_or_wrapper(self):
        lines=(HERE/'reports/gate-delta/corrupt.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VGD_BEGIN D '));_,end=delta.block(lines,start)
        with self.assertRaisesRegex(ValueError,'pair'):delta.separate(lines[:start]+lines[end:])
        start=next(i for i,l in enumerate(lines) if l.startswith('VGD_BEGIN D ') and int(l.split()[-1])>0);_,end=delta.block(lines,start)
        with self.assertRaises(ValueError):delta.block([l for l in lines[start:end] if not l.startswith('VXM_EVENT ')])
    def test_reference_cannot_reset_or_be_omitted(self):
        lines=(HERE/'reports/gate-delta/enabled.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VGD_BEGIN R '));_,end=delta.block(lines,start)
        with self.assertRaisesRegex(ValueError,'before reference'):delta.separate(lines[:start]+lines[end:])
        with self.assertRaisesRegex(ValueError,'reference reset'):delta.separate(lines[:end]+lines[start:end]+lines[end:])

if __name__=='__main__':unittest.main()
