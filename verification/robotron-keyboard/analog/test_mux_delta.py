"""Mux differences must preserve cache changes and complete wrapper lifetimes."""
import copy,json,unittest
from pathlib import Path
import mux_delta_probe as delta
import mux_delta_board as board
HERE=Path(__file__).resolve().parent

class MuxDelta(unittest.TestCase):
    def frames(self):
        lines=(HERE/'reports/mux-delta/enabled.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VXD_BEGIN '):
                frame,i=delta.block(lines,i);frames.append(frame)
            else:i+=1
        return frames
    def test_retained(self):
        for name,review in [('mux-delta',delta.review),('mux-partial-delta',delta.review),('mux-delta-budget',board.review)]:
            root=HERE/'reports'/name
            with self.subTest(name=name):self.assertEqual(review(root),json.loads((root/'assessment.json').read_text()))
    def test_splice_and_new_allocation(self):
        ref=self.frames()[0]['rows'];frame=dict(mode='D',tick=1,total=len(ref)+1,rows={},events=[])
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(ref,frame)
        row=next(iter(ref.values())).split();identity=max(ref)+1
        row[1]=str(identity);row[2]='0x110';row[3]='0x120';row[4]='0x128';row[5]='0x0'
        frame['rows'][identity]=(0,0,' '.join(row)+'\n')
        image=delta.reconstruct(ref,frame)
        self.assertEqual(delta.dense.parse(image)['muxes'][-1]['id'],identity)
        frame['rows'][identity]=(1,0,'x')
        with self.assertRaisesRegex(ValueError,'exceeds reference'):delta.reconstruct(ref,frame)
    def test_wrapper_records_are_not_inherited(self):
        frames=self.frames();ref=frames[0]['rows']
        queued=next(f for f in frames[1:] if f['events'])
        actual=delta.dense.parse(delta.reconstruct(ref,queued));self.assertTrue(actual['events'])
        bad=copy.deepcopy(queued);bad['events']=[]
        # Structurally readable corruption must remain observable, not be hidden
        # by inheriting previous wrapper records.
        other=delta.dense.parse(delta.reconstruct(ref,bad))
        self.assertNotEqual(actual,other);self.assertFalse(other['events'])
        with self.assertRaisesRegex(ValueError,'queue mismatch'):delta.dense.validate(other)
    def test_lost_fault_or_wrapper_rejected(self):
        lines=(HERE/'reports/mux-delta/corrupt.stdout').read_text().splitlines()
        # Remove one complete delta frame: dense pairing must fail.
        start=next(i for i,l in enumerate(lines) if l.startswith('VXD_BEGIN D '))
        _,end=delta.block(lines,start)
        with self.assertRaisesRegex(ValueError,'pair'):delta.separate(lines[:start]+lines[end:])
        index=next(i for i,l in enumerate(lines) if l.startswith('VXD_BEGIN D ') and int(l.split()[-1])>0)
        _,end=delta.block(lines,index)
        damaged=lines[index:end];damaged=[l for l in damaged if not l.startswith('VXM_EVENT ')]
        with self.assertRaises(ValueError):delta.block(damaged)
    def test_reference_lifecycle(self):
        lines=(HERE/'reports/mux-delta/enabled.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VXD_BEGIN R '));_,end=delta.block(lines,start)
        with self.assertRaisesRegex(ValueError,'before reference'):delta.separate(lines[:start]+lines[end:])
        with self.assertRaisesRegex(ValueError,'reference reset'):delta.separate(lines[:end]+lines[start:end]+lines[end:])

if __name__=='__main__':unittest.main()
