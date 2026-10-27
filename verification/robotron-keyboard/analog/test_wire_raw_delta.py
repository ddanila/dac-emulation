"""Lossless reduction differences must retain mutations and structural changes."""
import copy,json,unittest
from pathlib import Path
import wire_raw_delta_probe as delta
import wire_raw_delta_board as board
HERE=Path(__file__).resolve().parent
ROOT=HERE/'reports/wire-raw-delta'

class RawWireDeltaTests(unittest.TestCase):
    def frames(self):
        lines=(ROOT/'corrupt.stdout').read_text().splitlines();frames=[];i=0
        while i<len(lines):
            if lines[i].startswith('VWC_BEGIN '):
                frame,i=delta.block(lines,i);frames.append(frame)
            else:i+=1
        return frames

    def test_retained(self):
        self.assertEqual(delta.review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        root=HERE/'reports/wire-raw-delta-budget'
        self.assertEqual(board.review(root),json.loads((root/'assessment.json').read_text()))

    def test_incomplete_or_invalid_splice(self):
        frames=self.frames();reference=frames[0]['rows']
        frame=copy.deepcopy(frames[1]);frame['total']+=1
        with self.assertRaisesRegex(ValueError,'Missing new'):delta.reconstruct(reference,frame)
        frame=copy.deepcopy(next(f for f in frames[1:] if f['rows']))
        key=next(iter(frame['rows']));frame['rows'][key]=(len(reference[key])+1,0,'')
        with self.assertRaisesRegex(ValueError,'exceeds'):delta.reconstruct(reference,frame)

    def test_new_reduction_record(self):
        reference=self.frames()[0]['rows']
        identity=max(reference)+1
        parts=next(iter(reference.values())).splitlines()
        row=parts[0].split();row[1]=str(identity)
        row[2]='0x100000000000';row[3]='0x200000000000'
        parts[0]=' '.join(row);record='\n'.join(parts)+'\n'
        frame=dict(mode='D',tick=1,total=len(reference)+1,rows={identity:(0,0,record)})
        result=delta.reconstruct(reference,frame)
        self.assertEqual(delta.dense.parse(result)['filters'][-1]['id'],identity)

    def test_lost_fault(self):
        lines=(ROOT/'corrupt.stdout').read_text().splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VWC_BEGIN D ') and int(l.split()[-1])>0)
        frame,end=delta.block(lines,i)
        # Removing a changed row can leave syntactically valid data; exact dense pairing must catch it.
        replacement=[f"VWC_BEGIN D {frame['tick']} {frame['total']} 0",'VWC_END 0']
        with self.assertRaisesRegex(ValueError,'reconstruction changed'):
            delta.separate(lines[:i]+replacement+lines[end:])

    def test_reference_reset_and_truncation(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('VWC_BEGIN R '))
        _,end=delta.block(lines,i)
        with self.assertRaisesRegex(ValueError,'reference lifecycle'):delta.separate(lines[:end]+lines[i:end]+lines[end:])
        with self.assertRaises(ValueError):delta.block(lines[i:end-1])

if __name__=='__main__':unittest.main()
